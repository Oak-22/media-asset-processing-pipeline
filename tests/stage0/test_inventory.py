"""Tests for Stage 0 inventory building and shoot segmentation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from scripts.python.stage0.inventory import (
    build_card_files,
    filter_new,
    pairing_stem,
    scan_media,
    segment_shoots,
)

from .helpers import card_file


class SegmentShootsTest(unittest.TestCase):
    def test_splits_on_gap_longer_than_threshold(self) -> None:
        files = [
            card_file("JB000001.ARW", datetime(2026, 5, 10, 9, 0)),
            card_file("JB000002.ARW", datetime(2026, 5, 10, 11, 59)),
            card_file("JB000003.ARW", datetime(2026, 5, 10, 15, 30)),
        ]
        shoots = segment_shoots(files, gap_hours=3)
        self.assertEqual([len(shoot.files) for shoot in shoots], [2, 1])
        self.assertEqual(shoots[0].shoot_id, "2026-05-10_0900")
        self.assertEqual(shoots[1].shoot_id, "2026-05-10_1530")

    def test_gap_equal_to_threshold_stays_in_one_shoot(self) -> None:
        files = [
            card_file("JB000001.ARW", datetime(2026, 5, 10, 9, 0)),
            card_file("JB000002.ARW", datetime(2026, 5, 10, 12, 0)),
        ]
        self.assertEqual(len(segment_shoots(files, gap_hours=3)), 1)

    def test_date_change_splits_unless_disabled(self) -> None:
        files = [
            card_file("JB000001.ARW", datetime(2026, 5, 10, 23, 30)),
            card_file("JB000002.ARW", datetime(2026, 5, 11, 0, 15)),
        ]
        self.assertEqual(len(segment_shoots(files, gap_hours=3)), 2)
        self.assertEqual(
            len(segment_shoots(files, gap_hours=3, split_on_date_change=False)), 1
        )

    def test_sorts_unordered_input_and_counts_media(self) -> None:
        files = [
            card_file("C0001.MP4", datetime(2026, 5, 10, 10, 0), folder="PRIVATE/M4ROOT/CLIP"),
            card_file("JB000001.ARW", datetime(2026, 5, 10, 9, 0)),
            card_file("C0001M01.XML", datetime(2026, 5, 10, 10, 0), folder="PRIVATE/M4ROOT/CLIP"),
        ]
        (shoot,) = segment_shoots(files, gap_hours=3)
        self.assertEqual(shoot.files[0].source.name, "JB000001.ARW")
        self.assertEqual((shoot.photo_count, shoot.video_count), (1, 1))
        self.assertTrue(shoot.has_video)

    def test_empty_input(self) -> None:
        self.assertEqual(segment_shoots([], gap_hours=3), [])


class InventoryTest(unittest.TestCase):
    def test_pairing_stem_links_sony_clip_metadata(self) -> None:
        self.assertEqual(pairing_stem(Path("C0001M01.XML")), "c0001")
        self.assertEqual(pairing_stem(Path("C0001.MP4")), "c0001")
        self.assertEqual(pairing_stem(Path("JB000001.XMP")), "jb000001")

    def test_scan_and_capture_time_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dcim = root / "DCIM" / "100MSDCF"
            clip = root / "PRIVATE" / "M4ROOT" / "CLIP"
            thumbnails = root / "PRIVATE" / "M4ROOT" / "THMBNL"
            for folder in (dcim, clip, thumbnails):
                folder.mkdir(parents=True)
            for path in (
                dcim / "JB000001.ARW",
                dcim / "._JB000001.ARW",
                clip / "C0001.MP4",
                clip / "C0001M01.XML",
                thumbnails / "C0001T01.JPG",
                root / "DCIM" / "100MSDCF" / "notes.txt",
            ):
                path.write_bytes(b"x" * 10)
            paths = scan_media(root)
            self.assertEqual(
                [path.name for path in paths], ["JB000001.ARW", "C0001.MP4", "C0001M01.XML"]
            )
            metadata = {
                str(dcim / "JB000001.ARW"): {"DateTimeOriginal": "2026:05:10 09:00:00"},
                str(clip / "C0001.MP4"): {"CreateDate": "2026:05:10 09:30:00-07:00"},
                str(clip / "C0001M01.XML"): {"FileModifyDate": "2026:06:01 00:00:00-07:00"},
            }
            files = {item.source.name: item for item in build_card_files(root, paths, metadata)}
            self.assertEqual(files["JB000001.ARW"].capture_time_source, "exif_datetime_original")
            self.assertEqual(files["C0001.MP4"].capture_time, datetime(2026, 5, 10, 9, 30))
            self.assertEqual(files["C0001M01.XML"].capture_time_source, "paired_file")
            self.assertEqual(files["C0001M01.XML"].capture_time, datetime(2026, 5, 10, 9, 30))
            self.assertEqual(files["C0001M01.XML"].media, "video")

    def test_filter_new_uses_identity_keys(self) -> None:
        first = card_file("JB000001.ARW", datetime(2026, 5, 10, 9, 0))
        second = card_file("JB000002.ARW", datetime(2026, 5, 10, 9, 1))
        new, already = filter_new([first, second], {first.identity_key})
        self.assertEqual(new, [second])
        self.assertEqual(already, [first])


if __name__ == "__main__":
    unittest.main()
