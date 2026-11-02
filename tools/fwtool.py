#!/usr/bin/env python3
"""Inspect and verify ASUS HND (BCM4906) *_ubi.w firmware images offline.

Image layout, confirmed against official RT-AC86U 386_52334 and GT-AC2900
386_51582 images:

    JFFS2 bootfs | UBI (rootfs) | ... | vtoken (64 bytes) | WFI tag (20 bytes)

The WFI tag CRC is the complement of CRC32 over everything before the tag.
Never touches a router; uses only the standard library.
"""
import argparse
import hashlib
import json
import lzma
import os
import struct
import sys
import zlib

VTOKEN_SIZE = 64
WFI_SIZE = 20
TAIL_SIZE = VTOKEN_SIZE + WFI_SIZE
UBI_MAGIC = b"UBI#"
JFFS2_MAGIC = b"\x85\x19"
JFFS2_DIRENT = 0xE001
JFFS2_INODE = 0xE002
KERNEL_LZMA_OFFSET = 0x14

# WFI tag values shared by both official images.
EXPECTED_TAG = {"version": 0x5732, "chip": 0x4908, "flash": 3, "flags": 2}
# The RT-AC86U's own board ID. The kernel must know it: the board ID lives in
# the CFE NVRAM and this procedure never changes it.
REQUIRED_BOARD_ID = b"94906REF\0"
REQUIRED_BOOTFS = ("cferam.000", "vmlinux.lz", "94908.dtb")
# Images that also rewrite the bootloader or the whole flash are out of scope.
FORBIDDEN_NAME_PARTS = ("cferom", "pureubi", "puresqubi")
MIN_SIZE = 16 * 1024 * 1024
MAX_SIZE = 128 * 1024 * 1024
# These cferam builds differ by one pointer plus a build timestamp; the pointer
# only selects the model entry in combined-firmware (comfw) files.
KNOWN_CFERAM = {
    "6427360d3e10d507da1195ccfe1c8343fd8c187b068e1d1011f5f59945bc4b12": "RT-AC86U",
    "b184cbd565954e90f670d5e006ec129ca4fac3519054560efb6d425cebe474bb": "GT-AC2900",
}


class ImageError(Exception):
    pass


def parse_tail(data):
    if len(data) < TAIL_SIZE:
        raise ImageError("file too short to hold a vtoken and WFI tag")
    vtoken = data[-TAIL_SIZE:-WFI_SIZE]
    crc, version, chip, flash, flags = struct.unpack("<IIIII", data[-WFI_SIZE:])
    build, serial = struct.unpack("<HH", vtoken[4:8])
    product = vtoken[8:28].split(b"\0", 1)[0].rstrip(b" ")
    return {
        "firmware": ".".join(str(b) for b in vtoken[:4]),
        "build": build,
        "serial": serial,
        "productid": product.decode("ascii", "replace"),
        "tag": {
            "crc": crc,
            "version": version,
            "chip": chip,
            "flash": flash,
            "flags": flags,
        },
        "computed_crc": zlib.crc32(data[:-WFI_SIZE]) ^ 0xFFFFFFFF,
    }


def parse_bootfs(data):
    """Return {name: bytes or None}; None means an unsupported compressor."""
    end = data.find(UBI_MAGIC)
    if end < 0:
        raise ImageError("UBI# magic not found")
    names = {}
    chunks = {}
    pos = 0
    while pos + 12 <= end:
        if data[pos : pos + 2] != JFFS2_MAGIC:
            pos += 4
            continue
        node_type, total = struct.unpack("<HI", data[pos + 2 : pos + 8])
        if total < 12:
            raise ImageError(f"corrupt JFFS2 node at {pos:#x}")
        if node_type == JFFS2_DIRENT:
            ino, = struct.unpack("<I", data[pos + 20 : pos + 24])
            nsize = data[pos + 28]
            if ino:
                names[ino] = data[pos + 40 : pos + 40 + nsize].decode("ascii", "replace")
        elif node_type == JFFS2_INODE:
            ino, version = struct.unpack("<II", data[pos + 12 : pos + 20])
            isize, = struct.unpack("<I", data[pos + 28 : pos + 32])
            offset, csize = struct.unpack("<II", data[pos + 44 : pos + 52])
            compr = data[pos + 56]
            raw = data[pos + 68 : pos + 68 + csize]
            chunks.setdefault(ino, []).append((version, offset, compr, raw, isize))
        pos += (total + 3) & ~3

    files = {}
    for ino, name in names.items():
        parts = sorted(chunks.get(ino, []))
        if not parts:
            files[name] = b""
            continue
        out = bytearray(parts[-1][4])
        for _, offset, compr, raw, _ in parts:
            if compr == 0:
                body = raw
            elif compr == 6:
                body = zlib.decompress(raw)
            else:
                out = None
                break
            out[offset : offset + len(body)] = body
        files[name] = None if out is None else bytes(out)
    return files


def kernel_has_board_id(vmlinux):
    """True/False if decompressed; None if the kernel could not be decompressed."""
    if vmlinux is None or vmlinux[0xC:0x10] != b"BRCM":
        return None
    try:
        kernel = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(
            vmlinux[KERNEL_LZMA_OFFSET:]
        )
    except lzma.LZMAError:
        return None
    return REQUIRED_BOARD_ID in kernel


def inspect(path):
    with open(path, "rb") as fh:
        data = fh.read()
    info = parse_tail(data)
    info["path"] = path
    info["size"] = len(data)
    info["sha256"] = hashlib.sha256(data).hexdigest()
    bootfs = parse_bootfs(data)
    info["bootfs"] = {
        name: None if body is None else hashlib.sha256(body).hexdigest()
        for name, body in bootfs.items()
    }
    info["cferam_variant"] = KNOWN_CFERAM.get(info["bootfs"].get("cferam.000"), "unknown")
    info["kernel_has_board_id"] = kernel_has_board_id(bootfs.get("vmlinux.lz"))
    return info


def run_checks(info, expect, want_sha=None):
    tag = info["tag"]
    base = os.path.basename(info["path"]).lower()
    hit = [part for part in FORBIDDEN_NAME_PARTS if part in base]
    checks = [
        ("name is a plain firmware image", not hit, f"name contains {hit}" if hit else base),
        ("size is plausible", MIN_SIZE <= info["size"] <= MAX_SIZE, f"{info['size']} bytes"),
        (
            "productid matches",
            info["productid"] == expect,
            f"image={info['productid']!r} expected={expect!r}",
        ),
        (
            "WFI CRC matches",
            tag["crc"] == info["computed_crc"],
            f"tag={tag['crc']:#010x} computed={info['computed_crc']:#010x}",
        ),
    ]
    for key, value in EXPECTED_TAG.items():
        checks.append((f"WFI {key} matches", tag[key] == value, f"{tag[key]:#x}"))
    for name in REQUIRED_BOOTFS:
        checks.append((f"bootfs holds {name}", bool(info["bootfs"].get(name)), ""))
    has_board = info["kernel_has_board_id"]
    checks.append(
        (
            "kernel knows board ID 94906REF",
            has_board is True,
            "could not decompress kernel" if has_board is None else "",
        )
    )
    if want_sha:
        checks.append(
            ("SHA-256 matches", info["sha256"] == want_sha.lower(), info["sha256"])
        )
    return checks


def print_info(info):
    tag = info["tag"]
    print(f"file        {info['path']}")
    print(f"size        {info['size']}")
    print(f"sha256      {info['sha256']}")
    print(f"productid   {info['productid']}")
    print(f"version     {info['firmware']}.{info['build']}.{info['serial']}")
    print(
        f"wfi tag     version={tag['version']:#x} chip={tag['chip']:#x} "
        f"flash={tag['flash']} flags={tag['flags']}"
    )
    print(f"crc         tag={tag['crc']:#010x} computed={info['computed_crc']:#010x}")
    print(f"cferam      {info['cferam_variant']}")
    print(f"board id    94906REF in kernel: {info['kernel_has_board_id']}")
    for name, digest in sorted(info["bootfs"].items()):
        print(f"bootfs      {name:14} {(digest or 'unsupported compression')[:16]}")


def cmd_info(args):
    info = inspect(args.image)
    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
    else:
        print_info(info)
    return 0


def cmd_verify(args):
    info = inspect(args.image)
    checks = run_checks(info, args.expect, args.sha256)
    for label, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    failed = [label for label, passed, _ in checks if not passed]
    print(f"{'NOT SAFE TO USE' if failed else 'OK'}: {len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


def cmd_compare(args):
    left, right = inspect(args.left), inspect(args.right)
    print(f"{'':14} {left['productid']:18} {right['productid']:18}")
    print(f"{'version':14} {left['build']}.{left['serial']:<14} {right['build']}.{right['serial']:<14}")
    for name in sorted(set(left["bootfs"]) | set(right["bootfs"])):
        a, b = left["bootfs"].get(name), right["bootfs"].get(name)
        print(f"{name:14} {(a or '-')[:16]:18} {(b or '-')[:16]:18} {'same' if a == b else 'differs'}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("info", help="print image metadata")
    p.add_argument("image")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_info)
    p = sub.add_parser("verify", help="exit 0 only if every safety check passes")
    p.add_argument("image")
    p.add_argument("--expect", required=True, help="required productid, e.g. GT-AC2900")
    p.add_argument("--sha256", help="published SHA-256 of the .w file")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("compare", help="compare the bootfs of two images")
    p.add_argument("left")
    p.add_argument("right")
    p.set_defaults(func=cmd_compare)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ImageError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
