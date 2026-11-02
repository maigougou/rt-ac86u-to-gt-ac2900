import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, HERE)

import fwtool  # noqa: E402
import imagebuilder  # noqa: E402


class VerifyTests(unittest.TestCase):
    def run_verify(self, blob, expect="GT-AC2900", name="fw_ubi.w"):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, name)
            with open(path, "wb") as fh:
                fh.write(blob)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = fwtool.main(["verify", path, "--expect", expect])
            return code, out.getvalue()

    def assert_fails_on(self, label, **kwargs):
        verify_args = {k: kwargs.pop(k) for k in ("expect", "name") if k in kwargs}
        code, text = self.run_verify(imagebuilder.build(**kwargs), **verify_args)
        self.assertEqual(code, 1, text)
        self.assertIn(f"FAIL  {label}", text)

    def test_good_image_passes(self):
        code, text = self.run_verify(imagebuilder.build())
        self.assertEqual(code, 0, text)
        self.assertNotIn("FAIL", text)

    def test_wrong_model(self):
        self.assert_fails_on("productid matches", model="RT-AC86U")

    def test_bad_crc(self):
        self.assert_fails_on("WFI CRC matches", corrupt_crc=True)

    def test_wrong_chip(self):
        self.assert_fails_on("WFI chip matches", chip=0x4912)

    def test_missing_board_id(self):
        self.assert_fails_on("kernel knows board ID", board_id=b"GT-AC2900\0")

    def test_missing_bootfs_member(self):
        self.assert_fails_on("bootfs holds cferam.000", drop=("cferam.000",))

    def test_undecompressible_kernel_fails_closed(self):
        self.assert_fails_on("kernel knows board ID", drop=("vmlinux.lz",))

    def test_bootloader_image_rejected_by_name(self):
        self.assert_fails_on("name is a plain firmware image", name="GT-AC2900_cferom_ubi.w")

    def test_undersized_image(self):
        self.assert_fails_on("size is plausible", pad=1024)

    def test_sha256_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fw_ubi.w")
            with open(path, "wb") as fh:
                fh.write(imagebuilder.build())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    fwtool.main(["verify", path, "--expect", "GT-AC2900", "--sha256", "00"]), 1
                )

    def test_truncated_file_is_an_error_not_a_crash(self):
        code, text = self.run_verify(b"short")
        self.assertEqual(code, 2, text)


if __name__ == "__main__":
    unittest.main()
