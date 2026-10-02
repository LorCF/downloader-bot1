"""
Test suite for TimeParser, FFmpegHelper, DownloaderEngine, and CTkRangeSlider
"""
import unittest
import os
import customtkinter as ctk
from app import TimeParser, FFmpegHelper, DownloaderEngine, CTkRangeSlider, ModernDownloaderApp

class TestDownloaderComponents(unittest.TestCase):
    def test_time_parser(self):
        self.assertAlmostEqual(TimeParser.parse_time("00:01:20"), 80.0)
        self.assertAlmostEqual(TimeParser.parse_time("01:20"), 80.0)
        self.assertAlmostEqual(TimeParser.parse_time("80"), 80.0)
        self.assertAlmostEqual(TimeParser.parse_time("00:02:45"), 165.0)
        self.assertAlmostEqual(TimeParser.parse_time("1:00:00"), 3600.0)
        self.assertAlmostEqual(TimeParser.parse_time("01:30.5"), 90.5)
        self.assertIsNone(TimeParser.parse_time(""))
        self.assertIsNone(TimeParser.parse_time("   "))

        with self.assertRaises(ValueError):
            TimeParser.parse_time("invalid_time")

        with self.assertRaises(ValueError):
            TimeParser.parse_time("-10")

    def test_time_formatting(self):
        self.assertEqual(TimeParser.format_duration(80, force_hours=True), "00:01:20")
        self.assertEqual(TimeParser.format_duration(80, force_hours=False), "01:20")
        self.assertEqual(TimeParser.format_duration(3665, force_hours=True), "01:01:05")
        self.assertEqual(TimeParser.format_duration(None), "00:00:00")

    def test_byte_and_speed_formatting(self):
        self.assertEqual(TimeParser.format_bytes(1024), "1.0 KB")
        self.assertEqual(TimeParser.format_bytes(1048576), "1.0 MB")
        self.assertEqual(TimeParser.format_bytes(1073741824), "1.0 GB")

        self.assertEqual(TimeParser.format_speed(512000), "500.0 KB/s")
        self.assertEqual(TimeParser.format_speed(2097152), "2.00 MB/s")

    def test_ffmpeg_helper(self):
        path = FFmpegHelper.get_ffmpeg_path()
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))

    def test_range_slider_logic(self):
        root = ctk.CTk()
        slider = CTkRangeSlider(root, from_=0.0, to=388.0, start_val=64.0, end_val=268.0)
        root.update()
        st, et = slider.get_values()
        self.assertAlmostEqual(st, 64.0)
        self.assertAlmostEqual(et, 268.0)

        slider.set_values(10.0, 100.0, trigger_callback=False)
        st, et = slider.get_values()
        self.assertAlmostEqual(st, 10.0)
        self.assertAlmostEqual(et, 100.0)

        slider.set_range(0.0, 500.0, reset_values=True)
        st, et = slider.get_values()
        self.assertAlmostEqual(st, 0.0)
        self.assertAlmostEqual(et, 500.0)
        root.destroy()

    def test_app_lifecycle(self):
        app = ModernDownloaderApp()
        app.update()
        self.assertTrue(app.range_slider.is_enabled)
        self.assertEqual(app.start_time_entry.get(), "00:00:00")
        app.destroy()

if __name__ == "__main__":
    unittest.main()
