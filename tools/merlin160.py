#!/usr/bin/env python3
"""Patch an Asuswrt-Merlin 386.14_2 tree to build RT-AC86U firmware with 160 MHz.

The official RT-AC86U Wi-Fi firmware has no 160 MHz tables in its CLM regulatory
data, while the GT-AC2900 firmware, built from the same driver code, does. The
tree carries both as prebuilt objects, so the patch is two edits: use the GT
dhd.o for the RT build, and turn on BW160M so the host side will request 160 MHz.

Works on source trees and build output only; never touches a router.
"""
import argparse
import hashlib
import os
import re
import struct
import sys

DHD_DIR = "release/src/router/hnd_extra/prebuilt"
TARGET_MAK = "release/src-rt/target.mak"
RT_BUILD_NAME = b'BUILD_NAME="RT-AC86U"'
BW160M_FLAG = b"BW160M=y"
# dhd.o from tag 386.14_2. Any other tree may pair differently, so refuse it.
RT_DHD_SHA256 = "fa46d5e276c568ca553d904bc0bef4bcb85438b607a0f44e18bfa4d19ff94b61"
GT_DHD_SHA256 = "10254fe543ae569a2b426f796a2c51fa5e640f649483d1e7eaab87a18cfb3667"

DHD_KO = "lib/modules/4.1.27/extra/dhd.ko"
LIBSHARED = "usr/lib/libshared.so"
# Only present when the firmware was built with BW160M=y.
BW160M_MARKER = b"wl1_bw_160"

CLM_TAG = b"CLM DATA"
CLM_VERSION_OFFSET = 14
CLM_VERSION_SIZE = 20
CLM_POINTERS_OFFSET = 44
# Registry slots that only exist when the CLM data covers 160 MHz.
REGISTRY_SUBCHAN_160 = 15
REGISTRY_RANGES_160 = 18
REGISTRY_RATES_160 = 21
REGISTRY_SLOTS = 22
# Channel ranges are (first, last) byte pairs; 50 and 114 are the 160 MHz
# centers of channels 36-64 and 100-128.
REQUIRED_RANGES = ((50, 50), (114, 114))
RANGE_SCAN_PAIRS = 16


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_clm(blob):
    """Return {version, ranges, has_160} for the CLM data embedded in blob, or None."""
    for match in reversed(list(re.finditer(re.escape(CLM_TAG), blob))):
        offset = match.start()
        if offset + CLM_POINTERS_OFFSET + 8 > len(blob):
            continue
        self_ptr, registry_ptr = struct.unpack_from("<II", blob, offset + CLM_POINTERS_OFFSET)
        base = self_ptr - offset
        registry = registry_ptr - base
        if base < 0 or registry < 0 or registry + REGISTRY_SLOTS * 4 > len(blob):
            continue
        slots = struct.unpack_from(f"<{REGISTRY_SLOTS}I", blob, registry)
        raw = blob[offset + CLM_VERSION_OFFSET:offset + CLM_VERSION_OFFSET + CLM_VERSION_SIZE]
        ranges = []
        if slots[REGISTRY_RANGES_160]:
            start = slots[REGISTRY_RANGES_160] - base
            data = blob[start:start + RANGE_SCAN_PAIRS * 2]
            for first, last in zip(data[::2], data[1::2]):
                if first == 0:
                    break
                ranges.append((first, last))
        has_160 = (
            all(pair in ranges for pair in REQUIRED_RANGES)
            and slots[REGISTRY_SUBCHAN_160] != 0
            and slots[REGISTRY_RATES_160] != 0
        )
        return {
            "version": raw.split(b"\0")[0].decode("ascii", "replace"),
            "ranges": ranges,
            "has_160": has_160,
        }
    return None


def check_dhd(path):
    with open(path, "rb") as fh:
        clm = inspect_clm(fh.read())
    if clm is None:
        print(f"FAIL {path}: no CLM data found")
        return False
    print(f"INFO {path}: CLM {clm['version']}, 160 MHz ranges {clm['ranges']}")
    if not clm["has_160"]:
        print(f"FAIL {path}: CLM data has no 160 MHz tables")
        return False
    print(f"PASS {path}: CLM data has 160 MHz tables")
    return True


def patch_tree(tree):
    rt_dhd = os.path.join(tree, DHD_DIR, "RT-AC86U", "dhd.o")
    gt_dhd = os.path.join(tree, DHD_DIR, "GT-AC2900", "dhd.o")
    target_mak = os.path.join(tree, TARGET_MAK)
    for path in (rt_dhd, gt_dhd, target_mak):
        if not os.path.isfile(path):
            print(f"FAIL missing {path}: is this a Merlin source tree?")
            return 1
    gt_hash = sha256_of(gt_dhd)
    rt_hash = sha256_of(rt_dhd)
    if gt_hash != GT_DHD_SHA256 or rt_hash not in (RT_DHD_SHA256, GT_DHD_SHA256):
        print("FAIL dhd.o does not match tag 386.14_2; check out that tag first")
        return 1
    with open(target_mak, "rb") as fh:
        makefile = fh.read()
    if makefile.count(RT_BUILD_NAME) != 1:
        print(f'FAIL expected exactly one {RT_BUILD_NAME.decode()} in {TARGET_MAK}')
        return 1

    if rt_hash == GT_DHD_SHA256:
        print("INFO dhd.o already patched")
    else:
        with open(gt_dhd, "rb") as src, open(rt_dhd, "wb") as dst:
            dst.write(src.read())
        print("PASS replaced RT-AC86U/dhd.o with the GT-AC2900 copy")
    patched_name = RT_BUILD_NAME + b" " + BW160M_FLAG
    if patched_name in makefile:
        print("INFO target.mak already patched")
    else:
        with open(target_mak, "wb") as fh:
            fh.write(makefile.replace(RT_BUILD_NAME, patched_name))
        print("PASS added BW160M=y to the RT-AC86U target")
    return 0


def check_rootfs(rootfs):
    ok = check_dhd(os.path.join(rootfs, DHD_KO))
    with open(os.path.join(rootfs, LIBSHARED), "rb") as fh:
        if BW160M_MARKER in fh.read():
            print(f"PASS {LIBSHARED}: built with BW160M")
        else:
            print(f"FAIL {LIBSHARED}: not built with BW160M")
            ok = False
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("patch", help="apply the patch to a source tree").add_argument("tree")
    commands.add_parser("check-dhd", help="report the CLM data in a dhd.o or dhd.ko").add_argument("file")
    commands.add_parser("check-rootfs", help="check an extracted firmware rootfs").add_argument("rootfs")
    args = parser.parse_args(argv)
    try:
        if args.command == "patch":
            return patch_tree(args.tree)
        if args.command == "check-dhd":
            return 0 if check_dhd(args.file) else 1
        return check_rootfs(args.rootfs)
    except OSError as err:
        print(f"FAIL {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
