"""Runs router-check.sh under real POSIX shells, with fake router commands and /proc."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "tools", "router-check.sh")
SHELLS = [name for name in ("sh", "dash", "bash") if shutil.which(name)]

NVRAM_STUB = """#!/bin/sh
[ "$1" = get ] || exit 0
sed -n "s/^$2=//p" "$FAKE/nvram" | tail -n 1
"""
WL_STUB = """#!/bin/sh
[ -f "$FAKE/wl_dead" ] && exit 1
case "$3" in
ver) echo 7.14 ;;
country) echo "CN (CN/38) CHINA" ;;
chanspecs) printf '1\\n2\\n3\\n' ;;
txpwr_target_max) echo "Maximum Tx Power Target: 20.00" ;;
esac
"""


@unittest.skipIf(os.name == "nt" or not SHELLS, "needs a POSIX shell")
class RouterCheckTests(unittest.TestCase):
    def setUp(self):
        self.fake = tempfile.mkdtemp(prefix="router-check")
        self.addCleanup(shutil.rmtree, self.fake, ignore_errors=True)
        bin_dir = os.path.join(self.fake, "bin")
        os.makedirs(bin_dir)
        for name, body in (("nvram", NVRAM_STUB), ("wl", WL_STUB)):
            path = os.path.join(bin_dir, name)
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.write("mtd", 'dev:    size   erasesize  name\nmtd0: 00020000 00020000 "boot"\n')
        self.write("loadavg", "0.10 0.20 0.30 1/80 123\n")
        self.write("meminfo", "MemFree: 200000 kB\nCached: 100000 kB\n")
        self.write("syslog", "")
        self.write("libshared", "xx skip_crc xx")
        self.write("nvram", "productid=RT-AC86U\net0macaddr=AA:BB\n")
        self.env = dict(os.environ, FAKE=self.fake, PATH=bin_dir + os.pathsep + os.environ["PATH"])
        with open(SCRIPT) as fh:
            self.script = (
                fh.read()
                .replace("/proc/mtd", self.path("mtd"))
                .replace("/proc/loadavg", self.path("loadavg"))
                .replace("/proc/meminfo", self.path("meminfo"))
                .replace("/tmp/syslog.log", self.path("syslog"))
                .replace("/usr/lib/libshared.so", self.path("libshared"))
            )

    def path(self, name):
        return os.path.join(self.fake, name)

    def write(self, name, text):
        with open(self.path(name), "w") as fh:
            fh.write(text)

    def run_check(self, mode, shell):
        done = subprocess.run(
            [shell, "-s", mode],
            input=self.script,
            env=self.env,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return done.returncode, done.stdout

    def each_shell(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                yield shell

    def test_pre_passes_on_rt(self):
        for shell in self.each_shell():
            code, out = self.run_check("pre", shell)
            self.assertEqual(code, 0, out)
            self.assertIn("PASS firmware identifies as RT-AC86U", out)
            self.assertIn("INFO et0macaddr=AA:BB", out)
            self.assertIn("INFO eth6.chanspecs=3", out)
            self.assertIn("INFO mtd_table=mtd0=boot/00020000", out)
            self.assertIn("PASS this firmware has the skip_crc path", out)

    def test_pre_fails_on_other_model(self):
        self.write("nvram", "productid=RT-AC88U\n")
        for shell in self.each_shell():
            code, out = self.run_check("pre", shell)
            self.assertEqual(code, 1, out)
            self.assertIn("FAIL productid is 'RT-AC88U'", out)

    def test_dead_radio_fails(self):
        self.write("wl_dead", "")
        for shell in self.each_shell():
            code, out = self.run_check("pre", shell)
            self.assertEqual(code, 1, out)
            self.assertIn("FAIL radio eth5 does not respond", out)

    def test_empty_mtd_fails(self):
        self.write("mtd", "")
        for shell in self.each_shell():
            self.assertEqual(self.run_check("pre", shell)[0], 1)

    def test_missing_skip_crc_only_warns(self):
        self.write("libshared", "nothing here")
        for shell in self.each_shell():
            code, out = self.run_check("pre", shell)
            self.assertEqual(code, 0, out)
            self.assertIn("WARN skip_crc not found", out)

    def test_armed_flag_warns(self):
        self.write("nvram", "productid=RT-AC86U\nskip_crc=1\n")
        for shell in self.each_shell():
            self.assertIn("WARN skip_crc=1", self.run_check("pre", shell)[1])

    def test_post_warnings(self):
        self.write("nvram", "productid=GT-AC2900\naurargb_enable=1\n")
        self.write("syslog", "button TURBO pressed\n")
        for shell in self.each_shell():
            code, out = self.run_check("post", shell)
            self.assertEqual(code, 0, out)
            self.assertIn("PASS firmware identifies as GT-AC2900", out)
            self.assertIn("WARN aurargb_enable=1", out)
            self.assertIn("WARN syslog mentions TURBO", out)

    def test_post_fails_while_rt(self):
        for shell in self.each_shell():
            self.assertEqual(self.run_check("post", shell)[0], 1)


if __name__ == "__main__":
    unittest.main()
