#!/usr/bin/env python3
"""Workflow driver for converting an RT-AC86U to GT-AC2900 firmware and back.

Runs on Windows, Linux and macOS with Python 3.8+ and an OpenSSH client. It
never flashes: uploading the image stays a manual step.

Only "arm" and "disarm" change anything on the router, and they only change
the skip_crc nvram value, without committing it.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile

import fwtool

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROUTER_CHECK = os.path.join(TOOLS_DIR, "router-check.sh")
DEFAULT_STATE = os.path.join(os.path.dirname(TOOLS_DIR), "state")
SSH_COMMAND = ["ssh"]
SSH_CONNECTION_FAILED = 255
MANIFEST = "MANIFEST.sha256"
DUMP_ATTEMPTS = 3
TARGET_FOR = {"RT-AC86U": "GT-AC2900", "GT-AC2900": "RT-AC86U"}
# These identify the unit and must survive a firmware change.
IDENTITY_KEYS = ("label_mac", "et0macaddr", "0:macaddr", "1:macaddr", "serial_no", "territory_code")
RADIO_KEYS = (
    "eth5.country",
    "eth6.country",
    "eth5.chanspecs",
    "eth6.chanspecs",
    "eth5.txpwr_max",
    "eth6.txpwr_max",
)
MTD_LINE = re.compile(r'^(mtd\d+):\s+([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+"([^"]*)"', re.M)


class Die(Exception):
    pass


class Router:
    def __init__(self, host, socket_dir):
        if not host:
            raise Die("no router given: use --host or set RT_HOST, e.g. admin@192.168.50.1")
        self.host = host
        self.socket_dir = socket_dir

    def _argv(self, command):
        options = ["-o", "ConnectTimeout=10"]
        # Windows OpenSSH cannot multiplex; there, use an SSH key to avoid repeated prompts.
        if self.socket_dir:
            options += [
                "-o", "ControlMaster=auto",
                "-o", "ControlPath=" + os.path.join(self.socket_dir, "s"),
                "-o", "ControlPersist=120",
            ]
        return SSH_COMMAND + options + [self.host, command]

    def _spawn(self, command, stdout, stdin_bytes):
        try:
            done = subprocess.run(
                self._argv(command),
                input=stdin_bytes,
                stdin=None if stdin_bytes is not None else subprocess.DEVNULL,
                stdout=stdout,
            )
        except FileNotFoundError:
            raise Die("ssh not found: install an OpenSSH client (see docs/)")
        if done.returncode == SSH_CONNECTION_FAILED:
            raise Die(
                f"cannot connect to {self.host}. Check the address and that SSH is enabled. "
                "If ssh reported a changed host key after a factory reset, run: "
                f"ssh-keygen -R {self.host.split('@')[-1]}"
            )
        return done

    def run(self, command, stdin_bytes=None):
        done = self._spawn(command, subprocess.PIPE, stdin_bytes)
        return done.returncode, done.stdout

    def text(self, command):
        code, out = self.run(command)
        if code != 0:
            raise Die(f"router command failed ({code}): {command}")
        return out.decode("utf-8", "replace").strip()

    def dump(self, command, path):
        with open(path, "wb") as fh:
            return self._spawn(command, fh, None).returncode


def ensure_private_dir(path):
    os.makedirs(path, exist_ok=True)
    if os.name != "nt":
        os.chmod(path, 0o700)


def file_digest(path, algorithm):
    digest = hashlib.new(algorithm)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_report(router, state, mode):
    ensure_private_dir(state)
    with open(ROUTER_CHECK, "rb") as fh:
        # A Windows checkout may have CRLF line endings, which break ash.
        script = fh.read().replace(b"\r\n", b"\n")
    code, out = router.run(f"sh -s {mode}", stdin_bytes=script)
    with open(os.path.join(state, f"{mode}.txt"), "wb") as fh:
        fh.write(out)
    print(out.decode("utf-8", "replace"), end="")
    return code


def read_info(path):
    values = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("INFO ") and "=" in line:
                key, value = line[5:].rstrip("\r\n").split("=", 1)
                values.setdefault(key, value)
    return values


def cmd_check_fw(args):
    return fwtool.main(["verify", args.image, "--expect", args.model])


def cmd_pre(args, router):
    return 1 if run_report(router, args.state, "pre") else 0


def cmd_post(args, router):
    status = 1 if run_report(router, args.state, "post") else 0
    pre_path = os.path.join(args.state, "pre.txt")
    if not os.path.exists(pre_path):
        print("WARN no pre.txt to compare against")
        return status
    before = read_info(pre_path)
    after = read_info(os.path.join(args.state, "post.txt"))
    for key in IDENTITY_KEYS:
        if before.get(key) == after.get(key):
            print(f"PASS unchanged: {key}")
        else:
            print(f"FAIL changed: {key} ({before.get(key)!r} -> {after.get(key)!r})")
            status = 1
    for key in RADIO_KEYS:
        if before.get(key) != after.get(key):
            print(f"WARN radio differs: {key} ({before.get(key)!r} -> {after.get(key)!r})")
    return status


def dump_partition(router, dev, size, path):
    """Return True if stable; False if contents kept changing while being read."""
    for _ in range(DUMP_ATTEMPTS):
        code = router.dump(f"dd if=/dev/{dev} bs=131072 2>/dev/null", path)
        got = os.path.getsize(path)
        if code != 0 or got != size:
            raise Die(f"{dev}: got {got} of {size} bytes (exit {code}); backup failed, do not flash")
        remote = router.text(f"md5sum /dev/{dev}").split()[0]
        if remote == file_digest(path, "md5"):
            return True
    return False


def backup_dir(state):
    return os.path.join(state, "backup")


def write_manifest(folder):
    lines = []
    for root, _, names in os.walk(folder):
        for name in sorted(names):
            if name == MANIFEST:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder).replace(os.sep, "/")
            lines.append(f"{file_digest(path, 'sha256')}  ./{rel}\n")
    with open(os.path.join(folder, MANIFEST), "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(sorted(lines, key=lambda line: line[66:]))


def damaged_files(folder):
    damaged = []
    with open(os.path.join(folder, MANIFEST), encoding="utf-8") as fh:
        for line in fh:
            want, rel = line.rstrip("\n").split("  ", 1)
            path = os.path.join(folder, *rel[2:].split("/"))
            if not os.path.exists(path) or file_digest(path, "sha256") != want:
                damaged.append(rel)
    return damaged


def cmd_backup(args, router):
    ensure_private_dir(args.state)
    folder = backup_dir(args.state)
    ensure_private_dir(folder)
    manifest = os.path.join(folder, MANIFEST)
    if os.path.exists(manifest):
        os.remove(manifest)

    table = router.text("cat /proc/mtd")
    with open(os.path.join(folder, "proc_mtd.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(table + "\n")
    partitions = MTD_LINE.findall(table)
    if not partitions:
        raise Die("/proc/mtd lists no partitions; backup failed, do not flash")

    unstable = []
    for dev, hex_size, name in partitions:
        size = int(hex_size, 16)
        safe_name = re.sub(r"[^\w.-]", "_", name)
        print(f"dumping {dev} ({name}, {size} bytes)", flush=True)
        path = os.path.join(folder, f"{dev}-{safe_name}.bin")
        if not dump_partition(router, dev, size, path):
            unstable.append(f"{dev} {name}")
            print(f"WARN {dev} ({name}) changed while being read")

    code, nvram = router.run("nvram show 2>/dev/null")
    if code != 0 or not nvram:
        raise Die("nvram dump failed; backup failed, do not flash")
    with open(os.path.join(folder, "nvram.txt"), "wb") as fh:
        fh.write(nvram)
    if router.dump("tar -C /jffs -cf - . 2>/dev/null", os.path.join(folder, "jffs.tar")) != 0:
        print("WARN /jffs was not archived")

    if unstable:
        with open(os.path.join(folder, "unstable.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(unstable) + "\n")
        print("WARN partitions in use may not be a consistent snapshot; see unstable.txt")
    write_manifest(folder)
    print(f"backup complete: {folder}")
    print("It contains passwords and Wi-Fi keys. Keep it private, and copy it off this machine.")
    return 0


def cmd_arm(args, router):
    current = router.text("nvram get productid")
    target = TARGET_FOR.get(current)
    if not target:
        raise Die(f"router reports {current!r}; refusing to continue")
    if fwtool.main(["verify", args.image, "--expect", target]) != 0:
        raise Die("image failed verification; nothing changed")

    if target == "GT-AC2900":
        folder = backup_dir(args.state)
        if not os.path.exists(os.path.join(folder, MANIFEST)):
            raise Die("no backup found; run 'backup' first")
        damaged = damaged_files(folder)
        if damaged:
            raise Die(f"backup is damaged: {', '.join(damaged)}")

    print()
    print(f"Router: {current} -> {target}")
    print("This sets skip_crc=1 in RAM, so the next web UI upload skips both the model")
    print("check and the CRC check. One upload clears it. A reboot normally does too,")
    print("unless something commits nvram first, so run 'disarm' if you do not flash.")
    try:
        answer = input(f'Type "FLASH {target}" to continue: ')
    except EOFError:
        answer = ""
    if answer.strip() != f"FLASH {target}":
        raise Die("not confirmed; nothing changed")

    router.text("nvram set skip_crc=1")
    if router.text("nvram get skip_crc") != "1":
        raise Die("skip_crc did not read back as 1")
    print("Armed. Upload this exact file in Administration > Firmware Upgrade:")
    print(f"  {args.image}")
    return 0


def cmd_disarm(args, router):
    router.text("nvram set skip_crc=0")
    if router.text("nvram get skip_crc") != "0":
        raise Die("skip_crc did not read back as 0")
    print("Disarmed.")
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default=os.environ.get("RT_HOST"), help="user@address; defaults to $RT_HOST")
    common.add_argument("--state", default=os.environ.get("RT_STATE", DEFAULT_STATE), help="where reports and backups go")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check-fw", help="verify an image offline")
    p.add_argument("image")
    p.add_argument("model", choices=sorted(TARGET_FOR))
    p.set_defaults(offline=cmd_check_fw)
    p = sub.add_parser("pre", parents=[common], help="read-only report, saved as pre.txt")
    p.set_defaults(online=cmd_pre)
    p = sub.add_parser("backup", parents=[common], help="dump MTD partitions, nvram and /jffs")
    p.set_defaults(online=cmd_backup)
    p = sub.add_parser("arm", parents=[common], help="set skip_crc=1 after every gate passes")
    p.add_argument("image")
    p.set_defaults(online=cmd_arm)
    p = sub.add_parser("disarm", parents=[common], help="set skip_crc=0")
    p.set_defaults(online=cmd_disarm)
    p = sub.add_parser("post", parents=[common], help="read-only report, compared with pre.txt")
    p.set_defaults(online=cmd_post)
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        if hasattr(args, "offline"):
            return args.offline(args)
        with tempfile.TemporaryDirectory(prefix="ac86u2gt") as socket_dir:
            router = Router(args.host, None if os.name == "nt" else socket_dir)
            return args.online(args, router)
    except (Die, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
