"""Builds small synthetic firmware images with the layout fwtool.py expects."""
import lzma
import struct
import zlib

CHUNK = b"\xff" * 16


def _align(blob):
    return blob + b"\xff" * (-len(blob) & 3)


def _dirent(ino, name):
    raw = name.encode()
    total = 40 + len(raw)
    head = struct.pack("<HHII", 0x1985, 0xE001, total, 0)
    body = struct.pack("<IIIIBBHII", 1, 1, ino, 0, len(raw), 8, 0, 0, 0)
    return _align(head + body + raw)


def _inode(ino, data):
    total = 68 + len(data)
    head = struct.pack("<HHII", 0x1985, 0xE002, total, 0)
    body = struct.pack(
        "<IIIHHIIIIIIIBBHII",
        ino, 1, 0o100644, 0, 0, len(data), 0, 0, 0, 0, len(data), len(data), 0, 0, 0, 0, 0,
    )
    return _align(head + body + data)


def kernel(board_id=b"94906REF\0"):
    payload = b"\0" * 64 + board_id + b"Linux version 4.1.27\0"
    return b"\0" * 12 + b"BRCM" + b"\0" * 4 + lzma.compress(payload, format=lzma.FORMAT_ALONE)


def build(model="GT-AC2900", board_id=b"94906REF\0", corrupt_crc=False, drop=(), chip=0x4908, pad=17 * 1024 * 1024):
    files = {"94908.dtb": b"dtb", "cferam.000": b"cferam", "vmlinux.lz": kernel(board_id)}
    boot = b""
    for ino, (name, data) in enumerate(sorted(files.items()), start=2):
        if name in drop:
            continue
        boot += _dirent(ino, name) + _inode(ino, data)
    body = boot + b"UBI#" + b"\xff" * pad
    vtoken = bytes([3, 0, 0, 4]) + struct.pack("<HH", 386, 51582)
    vtoken += model.encode().ljust(20, b"\0")
    vtoken = vtoken.ljust(64, b"\0")
    body += vtoken
    crc = zlib.crc32(body) ^ 0xFFFFFFFF
    if corrupt_crc:
        crc ^= 1
    return body + struct.pack("<IIIII", crc, 0x5732, chip, 3, 2)
