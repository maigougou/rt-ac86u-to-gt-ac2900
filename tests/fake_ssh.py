"""Stands in for ssh in the driver tests, with no shell, so it also runs on Windows.

Usage: fake_ssh.py FAKE_DIR [ssh options] HOST COMMAND
FAKE_DIR holds the fake router: an "nvram" file, mtdN files, a "mtd" table, and
flag files (unreachable, md5_wrong, short_dump, radio_dead).
"""
import hashlib
import io
import os
import re
import sys
import tarfile

fake = sys.argv[1]
command = sys.argv[-1]
out = sys.stdout.buffer


def flag(name):
    return os.path.exists(os.path.join(fake, name))


def nvram():
    values = {}
    with open(os.path.join(fake, "nvram"), encoding="utf-8") as fh:
        for line in fh:
            key, _, value = line.rstrip("\n").partition("=")
            values[key] = value
    return values


def report(mode):
    script = sys.stdin.buffer.read()
    if b"\r" in script:
        sys.exit(3)
    values = nvram()
    with open(os.path.join(fake, "chanspecs"), encoding="utf-8") as fh:
        chanspecs = fh.read().strip()
    lines = [f"INFO {key}={value}" for key, value in values.items()]
    lines += [f"INFO eth6.chanspecs={chanspecs}", "INFO eth5.country=CN"]
    wanted = "RT-AC86U" if mode == "pre" else "GT-AC2900"
    failed = values.get("productid") != wanted or flag("radio_dead")
    lines.append("FAIL check" if failed else "PASS check")
    out.write(("\n".join(lines) + "\n").encode())
    sys.exit(1 if failed else 0)


def main():
    if flag("unreachable"):
        sys.exit(255)
    if command.startswith("sh -s "):
        report(command.split()[-1])
    if command == "cat /proc/mtd":
        with open(os.path.join(fake, "mtd"), "rb") as fh:
            out.write(fh.read())
        return
    match = re.match(r"dd if=/dev/(mtd\d+) ", command)
    if match:
        with open(os.path.join(fake, match.group(1)), "rb") as fh:
            data = fh.read()
        out.write(data[:-1024] if flag("short_dump") else data)
        return
    match = re.match(r"md5sum /dev/(mtd\d+)$", command)
    if match:
        with open(os.path.join(fake, match.group(1)), "rb") as fh:
            digest = hashlib.md5(fh.read()).hexdigest()
        out.write(f"{'0' * 32 if flag('md5_wrong') else digest}  /dev/x\n".encode())
        return
    match = re.match(r"nvram get (\S+)$", command)
    if match:
        out.write((nvram().get(match.group(1), "") + "\n").encode())
        return
    match = re.match(r"nvram set (\S+)=(\S*)$", command)
    if match:
        with open(os.path.join(fake, "nvram"), "a", encoding="utf-8") as fh:
            fh.write(f"{match.group(1)}={match.group(2)}\n")
        return
    if command.startswith("nvram show"):
        out.write(("\n".join(f"{k}={v}" for k, v in nvram().items()) + "\n").encode())
        return
    if command.startswith("tar -C /jffs"):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo("note")
            info.size = 5
            tar.addfile(info, io.BytesIO(b"hello"))
        out.write(buf.getvalue())
        return
    sys.exit(127)


main()
