"""End-to-end tests of ac86u2gt.py against a fake router; touches no real device."""
import contextlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, HERE)

import ac86u2gt  # noqa: E402
import imagebuilder  # noqa: E402

MTD_TABLE = (
    "dev:    size   erasesize  name\n"
    'mtd0: 00020000 00020000 "boot"\n'
    'mtd1: 00040000 00020000 "misc1"\n'
)
RT_NVRAM = {
    "productid": "RT-AC86U",
    "territory_code": "CN/01",
    "label_mac": "AA:BB:CC:00:00:01",
    "et0macaddr": "AA:BB:CC:00:00:01",
    "0:macaddr": "AA:BB:CC:00:00:02",
    "1:macaddr": "AA:BB:CC:00:00:03",
    "serial_no": "TESTSERIAL",
}


class DriverTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ac86u2gt-test")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fake = os.path.join(self.tmp, "fake")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.fake)
        self.write("mtd", MTD_TABLE)
        self.write("chanspecs", "8")
        with open(os.path.join(self.fake, "mtd0"), "wb") as fh:
            fh.write(b"\0" * 0x20000)
        with open(os.path.join(self.fake, "mtd1"), "wb") as fh:
            fh.write(os.urandom(0x40000))
        with open(os.path.join(self.fake, "nvram"), "w", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in RT_NVRAM.items())
        patcher = mock.patch.object(
            ac86u2gt, "SSH_COMMAND", [sys.executable, os.path.join(HERE, "fake_ssh.py"), self.fake]
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.gt_image = self.image("GT-AC2900_ubi.w", imagebuilder.build("GT-AC2900"))
        self.rt_image = self.image("RT-AC86U_ubi.w", imagebuilder.build("RT-AC86U"))
        self.bad_image = self.image("bad_ubi.w", imagebuilder.build("GT-AC2900", corrupt_crc=True))

    def write(self, name, text=""):
        with open(os.path.join(self.fake, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def remove(self, name):
        os.remove(os.path.join(self.fake, name))

    def image(self, name, blob):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    def nv(self, key):
        value = None
        with open(os.path.join(self.fake, "nvram"), encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.rstrip("\n").partition("=")
                if k == key:
                    value = v
        return value

    def set_nv(self, key, value):
        with open(os.path.join(self.fake, "nvram"), "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")

    def tool(self, *args, answer=None, host="stub@fake"):
        command = args[0]
        argv = [command]
        if command != "check-fw":
            argv += ["--state", self.state]
            if host:
                argv += ["--host", host]
        argv += list(args[1:])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with mock.patch("builtins.input", side_effect=[answer] if answer else EOFError):
                code = ac86u2gt.main(argv)
        return code, out.getvalue() + err.getvalue()

    def backed_up(self):
        code, text = self.tool("backup")
        self.assertEqual(code, 0, text)
        return os.path.join(self.state, "backup")


class CheckFwTests(DriverTestCase):
    def test_accepts_good_image(self):
        self.assertEqual(self.tool("check-fw", self.gt_image, "GT-AC2900")[0], 0)

    def test_rejects_corrupt_image(self):
        self.assertEqual(self.tool("check-fw", self.bad_image, "GT-AC2900")[0], 1)


class ReportTests(DriverTestCase):
    def test_host_is_mandatory(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("RT_HOST", None)
            code, text = self.tool("pre", host=None)
        self.assertEqual(code, 1)
        self.assertIn("no router given", text)

    def test_pre_passes_and_saves_report(self):
        code, text = self.tool("pre")
        self.assertEqual(code, 0, text)
        self.assertIn("INFO et0macaddr=AA:BB:CC:00:00:01", text)
        self.assertTrue(os.path.exists(os.path.join(self.state, "pre.txt")))

    def test_pre_fails_when_router_reports_failure(self):
        self.write("radio_dead")
        self.assertEqual(self.tool("pre")[0], 1)

    def test_connection_failure_explains_host_key_fix(self):
        self.write("unreachable")
        code, text = self.tool("pre")
        self.assertEqual(code, 1)
        self.assertIn("ssh-keygen -R fake", text)

    def test_crlf_script_is_normalized(self):
        crlf = os.path.join(self.tmp, "crlf.sh")
        with open(crlf, "wb") as fh:
            fh.write(b"#!/bin/sh\r\necho hi\r\n")
        with mock.patch.object(ac86u2gt, "ROUTER_CHECK", crlf):
            code, text = self.tool("pre")
        self.assertEqual(code, 0, text)

    def test_missing_ssh_is_explained(self):
        with mock.patch.object(ac86u2gt, "SSH_COMMAND", ["no-such-ssh-binary"]):
            code, text = self.tool("pre")
        self.assertEqual(code, 1)
        self.assertIn("ssh not found", text)


class BackupTests(DriverTestCase):
    def test_backup_is_complete_and_exact(self):
        folder = self.backed_up()
        with open(os.path.join(folder, "mtd1-misc1.bin"), "rb") as got:
            with open(os.path.join(self.fake, "mtd1"), "rb") as want:
                self.assertEqual(got.read(), want.read())
        with tarfile.open(os.path.join(folder, "jffs.tar")) as tar:
            self.assertIn("note", tar.getnames())
        with open(os.path.join(folder, "nvram.txt"), encoding="utf-8") as fh:
            self.assertIn("productid=RT-AC86U", fh.read())
        with open(os.path.join(folder, ac86u2gt.MANIFEST), encoding="utf-8") as fh:
            manifest = fh.read()
        self.assertIn("./mtd0-boot.bin", manifest)
        self.assertNotIn(ac86u2gt.MANIFEST, manifest)
        self.assertEqual(ac86u2gt.damaged_files(folder), [])

    def test_short_dump_aborts(self):
        self.write("short_dump")
        code, text = self.tool("backup")
        self.assertEqual(code, 1)
        self.assertIn("do not flash", text)
        self.assertFalse(
            os.path.exists(os.path.join(self.state, "backup", ac86u2gt.MANIFEST))
        )

    def test_changing_partition_is_reported_not_fatal(self):
        self.write("md5_wrong")
        code, text = self.tool("backup")
        self.assertEqual(code, 0, text)
        self.assertIn("changed while being read", text)
        self.assertTrue(os.path.exists(os.path.join(self.state, "backup", "unstable.txt")))

    def test_odd_partition_names_are_sanitized(self):
        self.write("mtd", MTD_TABLE.replace('"misc1"', '"a:b/c"'))
        folder = self.backed_up()
        self.assertTrue(os.path.exists(os.path.join(folder, "mtd1-a_b_c.bin")))


class ArmTests(DriverTestCase):
    def arm(self, image, answer="FLASH GT-AC2900"):
        return self.tool("arm", image, answer=answer)

    def test_refuses_without_backup(self):
        code, text = self.arm(self.gt_image)
        self.assertEqual(code, 1)
        self.assertIn("no backup found", text)
        self.assertIsNone(self.nv("skip_crc"))

    def test_refuses_wrong_model_or_corrupt_image(self):
        self.backed_up()
        self.assertEqual(self.arm(self.rt_image)[0], 1)
        self.assertEqual(self.arm(self.bad_image)[0], 1)
        self.assertIsNone(self.nv("skip_crc"))

    def test_refuses_wrong_or_missing_confirmation(self):
        self.backed_up()
        self.assertEqual(self.arm(self.gt_image, answer="yes")[0], 1)
        self.assertEqual(self.tool("arm", self.gt_image)[0], 1)
        self.assertIsNone(self.nv("skip_crc"))

    def test_refuses_damaged_backup(self):
        folder = self.backed_up()
        with open(os.path.join(folder, "mtd0-boot.bin"), "ab") as fh:
            fh.write(b"x")
        code, text = self.arm(self.gt_image)
        self.assertEqual(code, 1)
        self.assertIn("backup is damaged", text)

    def test_refuses_unknown_router(self):
        self.backed_up()
        self.set_nv("productid", "RT-AC88U")
        self.assertEqual(self.arm(self.gt_image)[0], 1)

    def test_arm_then_disarm(self):
        self.backed_up()
        code, text = self.arm(self.gt_image)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.nv("skip_crc"), "1")
        self.assertEqual(self.tool("disarm")[0], 0)
        self.assertEqual(self.nv("skip_crc"), "0")

    def test_rollback_direction_needs_the_rt_image(self):
        self.set_nv("productid", "GT-AC2900")
        self.assertEqual(self.tool("arm", self.gt_image, answer="FLASH RT-AC86U")[0], 1)
        self.assertEqual(self.tool("arm", self.rt_image, answer="FLASH RT-AC86U")[0], 0)
        self.assertEqual(self.nv("skip_crc"), "1")


class PostTests(DriverTestCase):
    def convert(self):
        self.assertEqual(self.tool("pre")[0], 0)
        self.set_nv("productid", "GT-AC2900")

    def test_fails_while_still_rt(self):
        self.tool("pre")
        self.assertEqual(self.tool("post")[0], 1)

    def test_passes_and_reports_radio_changes(self):
        self.convert()
        self.write("chanspecs", "16")
        code, text = self.tool("post")
        self.assertEqual(code, 0, text)
        self.assertIn("PASS unchanged: et0macaddr", text)
        self.assertIn("WARN radio differs: eth6.chanspecs", text)

    def test_fails_when_mac_changed(self):
        self.convert()
        self.set_nv("et0macaddr", "AA:BB:CC:00:00:FF")
        code, text = self.tool("post")
        self.assertEqual(code, 1)
        self.assertIn("FAIL changed: et0macaddr", text)


if __name__ == "__main__":
    unittest.main()
