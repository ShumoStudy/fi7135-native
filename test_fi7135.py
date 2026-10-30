#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_fi7135.py — fi7135_native 的单元测试（模拟 scanimage，无需真机）。

运行：python3 test_fi7135.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fi7135_native as app  # noqa: E402

SAMPLE_SCANIMAGE_L = """device `fujitsu:libusb:002:003' is a FUJITSU fi-7135 scanner
device `epson2:libusb:003:002' is a Epson GT-X900 scanner
"""

SAMPLE_NO_DEVICE = "No scanners were identified. (If this is not what you expected,\n" \
                   "make sure that the scanner is connected, turned on and detected\n" \
                   "by the appropriate kernel drivers.)"


class TestDetect(unittest.TestCase):
    def test_parse_devices(self):
        proc = mock.Mock()
        proc.stdout = SAMPLE_SCANIMAGE_L
        proc.stderr = ""
        with mock.patch.object(subprocess, "run", return_value=proc):
            devices, _ = app.detect_scanners()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0][0], "fujitsu:libusb:002:003")
        self.assertIn("fi-7135", devices[0][1])

    def test_no_devices_graceful(self):
        proc = mock.Mock()
        proc.stdout = SAMPLE_NO_DEVICE
        proc.stderr = ""
        with mock.patch.object(subprocess, "run", return_value=proc):
            devices, _ = app.detect_scanners()
        self.assertEqual(devices, [])

    def test_scanimage_missing(self):
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError):
            devices, err = app.detect_scanners()
        self.assertIsNone(devices)
        self.assertIn("sane-utils", err)

    def test_find_fi7135_prefers_fi7135(self):
        devices = [
            ("epson2:libusb:003:002", "Epson GT-X900"),
            ("fujitsu:libusb:002:003", "FUJITSU fi-7135"),
        ]
        self.assertEqual(app.find_fi7135(devices), "fujitsu:libusb:002:003")


class TestBuildCmd(unittest.TestCase):
    def test_batch_adf(self):
        cmd = app.build_scan_cmd(
            "fujitsu:libusb:002:003",
            source="ADF Duplex", resolution=300, mode="Color",
            out_prefix="/tmp/x/page-%04d.tif",
        )
        self.assertIn("--batch=/tmp/x/page-%04d.tif", cmd)
        self.assertIn("--source", cmd)
        self.assertIn("ADF Duplex", cmd)

    def test_flatbed_single(self):
        cmd = app.build_scan_cmd("dev", source="Flatbed", resolution=600)
        self.assertEqual(cmd[0], app.SCANIMAGE)
        self.assertNotIn("--batch", cmd)

    def test_brightness_optional(self):
        cmd = app.build_scan_cmd("dev", source="Flatbed", brightness=None)
        self.assertNotIn("--brightness", cmd)
        cmd2 = app.build_scan_cmd("dev", source="Flatbed", brightness=128)
        self.assertIn("--brightness", cmd2)


class TestSources(unittest.TestCase):
    def test_get_sources_adf_only(self):
        # 真实 fi-7135 的 --help 片段
        help_text = (
            "    --source ADF Front|ADF Back|ADF Duplex [ADF Front]\n"
            "        Selects the scan source (such as a document-feeder).\n"
            "    --mode Lineart|Halftone|Gray|Color [Lineart]\n"
        )
        with mock.patch.object(app, "device_options", return_value=help_text):
            sources = app.get_sources("fujitsu:fi-7135:409163")
        self.assertEqual(sources, ["ADF Front", "ADF Back", "ADF Duplex"])

    def test_get_sources_fallback_empty(self):
        with mock.patch.object(app, "device_options", return_value="no options here"):
            self.assertEqual(app.get_sources("dev"), [])


class TestPostProcess(unittest.TestCase):
    def test_default_out_dir_is_documents(self):
        import os as _os
        self.assertEqual(app.DEFAULT_OUT_DIR, _os.path.expanduser("~/Documents"))

    def test_is_blank_judgement(self):
        from PIL import Image, ImageDraw
        blank = Image.new("L", (100, 100), 255)
        self.assertTrue(app._is_blank(blank, 1.0))
        im = Image.new("L", (100, 100), 255)
        ImageDraw.Draw(im).rectangle([0, 0, 50, 50], fill=0)  # 25% 墨水
        self.assertFalse(app._is_blank(im, 1.0))

    def test_blank_removal_drops_white_page(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            blank = os.path.join(tmp, "p1.tif")
            text = os.path.join(tmp, "p2.tif")
            Image.new("L", (200, 200), 255).save(blank, "TIFF")
            im = Image.new("L", (200, 200), 255)
            from PIL import ImageDraw
            ImageDraw.Draw(im).rectangle([10, 10, 180, 60], fill=0)
            im.save(text, "TIFF")
            kept, removed = app._process_pages(
                [blank, text], mode="Gray", blank_removal=True, enhance=False)
            self.assertEqual(removed, [1])
            self.assertEqual(kept, [text])

    def test_blank_removal_off_keeps_all(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            blank = os.path.join(tmp, "p1.tif")
            Image.new("L", (200, 200), 255).save(blank, "TIFF")
            kept, removed = app._process_pages(
                [blank], mode="Gray", blank_removal=False, enhance=False)
            self.assertEqual(removed, [])
            self.assertEqual(kept, [blank])

    def test_enhance_spreads_histogram(self):
        from PIL import Image, ImageDraw
        im = Image.new("L", (100, 100), 126)
        ImageDraw.Draw(im).rectangle([10, 10, 40, 40], fill=128)
        out = app._enhance_image(im)
        hist = out.histogram()
        dark = sum(hist[:100])
        light = sum(hist[180:])
        self.assertGreater(dark, 0, "增强后应出现深色像素")
        self.assertGreater(light, 0, "增强后应出现亮色像素")


class TestScanFlow(unittest.TestCase):
    def test_scan_flatbed_to_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd, **kw):
                # 单页模式：cmd 最后一项就是 scanimage 要写入的 tiff 路径
                from PIL import Image
                Image.new("RGB", (100, 140), "white").save(cmd[-1], "TIFF")
                proc = mock.Mock()
                proc.returncode = 0
                proc.stdout = ""
                proc.stderr = ""
                return proc

            with mock.patch.object(subprocess, "run", side_effect=fake_run):
                results, err = app.scan(
                    "fujitsu:libusb:002:003", source="Flatbed",
                    resolution=300, mode="Color", fmt="pdf", out_dir=tmp,
                    name="test_page", blank_removal=False, enhance=False,
                )
            self.assertIsNone(err, err)
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].endswith("test_page.pdf"))
            self.assertTrue(os.path.exists(results[0]))
            self.assertGreater(os.path.getsize(results[0]), 0)

    def test_scan_adf_batch_to_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd, **kw):
                from PIL import Image
                # 批量模式：解析 --batch=pattern 生成 3 页 tiff
                pattern = next(
                    a.split("=", 1)[1] for a in cmd if a.startswith("--batch=")
                )
                for i in (1, 2, 3):
                    Image.new("RGB", (80, 110), (i * 40, 90, 150)).save(
                        pattern % i, "TIFF"
                    )
                proc = mock.Mock()
                proc.returncode = 0
                proc.stdout = ""
                proc.stderr = ""
                return proc

            with mock.patch.object(subprocess, "run", side_effect=fake_run):
                results, err = app.scan(
                    "fujitsu:libusb:002:003", source="ADF Duplex",
                    resolution=200, mode="Gray", fmt="jpg", out_dir=tmp,
                    name="batch_test", blank_removal=False, enhance=False,
                )
            self.assertIsNone(err, err)
            self.assertEqual(len(results), 3)
            for r in results:
                self.assertTrue(os.path.exists(r))
            self.assertTrue(results[0].endswith("batch_test_p01.jpg"))

    def test_scan_returns_error_on_failure(self):
        proc = mock.Mock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "scanimage: open of device failed: Invalid argument"
        with mock.patch.object(subprocess, "run", return_value=proc):
            results, err = app.scan("dev", source="Flatbed", fmt="pdf", out_dir=tempfile.gettempdir())
        self.assertIsNone(results)
        self.assertIn("扫描失败", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
