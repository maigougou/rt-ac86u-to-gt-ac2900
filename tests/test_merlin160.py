import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import merlin160  # noqa: E402

BASE = 0x200000


def clm_blob(with_160=True):
    """Fake dongle image: a stray tag, then a CLM header, registry and ranges."""
    blob = bytearray(b"\0" * 16 + b"CLM DATA" + b"\0" * 0x40)
    header = len(blob)
    blob += b"CLM DATA\0\0" + b"\x12\0\0\0" + b"9.11.6".ljust(30, b"\0")
    registry = header + 52
    blob += struct.pack("<II", BASE + header, BASE + registry)
    ranges = registry + merlin160.REGISTRY_SLOTS * 4
    slots = [BASE + 4] * merlin160.REGISTRY_SLOTS
    if not with_160:
        for slot in (15, 18, 21):
            slots[slot] = 0
    else:
        slots[18] = BASE + ranges
    blob += struct.pack(f"<{merlin160.REGISTRY_SLOTS}I", *slots)
    blob += bytes([50, 50, 50, 114, 114, 114, 0, 0])
    return bytes(blob)


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = merlin160.main(list(argv))
    return code, out.getvalue()


class ClmTests(unittest.TestCase):
    def test_reads_version_and_ranges(self):
        clm = merlin160.inspect_clm(clm_blob())
        self.assertEqual(clm["version"], "9.11.6")
        self.assertEqual(clm["ranges"], [(50, 50), (50, 114), (114, 114)])
        self.assertTrue(clm["has_160"])

    def test_null_tables_mean_no_160(self):
        clm = merlin160.inspect_clm(clm_blob(with_160=False))
        self.assertEqual(clm["ranges"], [])
        self.assertFalse(clm["has_160"])

    def test_no_clm_data(self):
        self.assertIsNone(merlin160.inspect_clm(b"\0" * 256))


class TreeTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tree = tmp.name

    def write(self, relative, data):
        path = os.path.join(self.tree, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def read(self, relative):
        with open(os.path.join(self.tree, relative), "rb") as fh:
            return fh.read()


class PatchTests(TreeTestCase):
    RT = "release/src/router/hnd_extra/prebuilt/RT-AC86U/dhd.o"
    GT = "release/src/router/hnd_extra/prebuilt/GT-AC2900/dhd.o"
    MAK = "release/src-rt/target.mak"
    MAK_TEXT = b'export RT-AC86U += BUILD_NAME="RT-AC86U" NVSIZE="128" \\\nDHDAP=y\n'

    def setUp(self):
        super().setUp()
        self.write(self.RT, b"rt")
        self.write(self.GT, b"gt")
        self.write(self.MAK, self.MAK_TEXT)
        hashes = {"RT_DHD_SHA256": merlin160.sha256_of(os.path.join(self.tree, self.RT)),
                  "GT_DHD_SHA256": merlin160.sha256_of(os.path.join(self.tree, self.GT))}
        patcher = mock.patch.multiple(merlin160, **hashes)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_applies_both_edits(self):
        code, text = run("patch", self.tree)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.read(self.RT), b"gt")
        self.assertIn(b'BUILD_NAME="RT-AC86U" BW160M=y NVSIZE', self.read(self.MAK))

    def test_second_run_changes_nothing(self):
        run("patch", self.tree)
        before = self.read(self.MAK)
        code, text = run("patch", self.tree)
        self.assertEqual(code, 0, text)
        self.assertIn("already patched", text)
        self.assertEqual(self.read(self.MAK), before)

    def test_refuses_other_source_versions(self):
        self.write(self.GT, b"from another tag")
        code, text = run("patch", self.tree)
        self.assertEqual(code, 1)
        self.assertIn("386.14_2", text)
        self.assertEqual(self.read(self.RT), b"rt")
        self.assertEqual(self.read(self.MAK), self.MAK_TEXT)

    def test_refuses_ambiguous_makefile(self):
        self.write(self.MAK, self.MAK_TEXT * 2)
        self.assertEqual(run("patch", self.tree)[0], 1)
        self.assertEqual(self.read(self.RT), b"rt")

    def test_missing_tree_is_explained(self):
        code, text = run("patch", os.path.join(self.tree, "nope"))
        self.assertEqual(code, 1)
        self.assertIn("missing", text)


class RootfsTests(TreeTestCase):
    def rootfs(self, dhd, libshared):
        self.write(merlin160.DHD_KO, dhd)
        self.write(merlin160.LIBSHARED, libshared)
        return run("check-rootfs", self.tree)

    def test_passes_when_both_parts_present(self):
        code, text = self.rootfs(clm_blob(), b"x\0wl1_bw_160\0")
        self.assertEqual(code, 0, text)

    def test_fails_without_160_tables(self):
        code, text = self.rootfs(clm_blob(with_160=False), b"x\0wl1_bw_160\0")
        self.assertEqual(code, 1)
        self.assertIn("no 160 MHz tables", text)

    def test_fails_without_bw160m(self):
        code, text = self.rootfs(clm_blob(), b"x\0")
        self.assertEqual(code, 1)
        self.assertIn("not built with BW160M", text)

    def test_missing_rootfs_files_are_reported(self):
        code, text = run("check-rootfs", self.tree)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", text)


if __name__ == "__main__":
    unittest.main()
