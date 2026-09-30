"""Tests for Stage 0 copy, hash verification, ledger, and collision refusal."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from scripts.python.stage0.inventory import filter_new
from scripts.python.stage0.transfer import (
    CollisionError,
    OffloadLedger,
    copy_verified,
    transfer_files,
)

from .helpers import card_file


class TransferTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.card = base / "card"
        self.ssd = base / "ssd"
        self.ledger = OffloadLedger(base / "state" / "ledger.jsonl")
        self.shoot_dir = self.ssd / "Automotive" / "Nascar – Sonoma, CA"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make(self, name: str, content: bytes, folder: str = "DCIM/100MSDCF"):
        path = self.card / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return card_file(
            name,
            datetime(2026, 5, 10, 9, 0),
            root=self.card,
            folder=folder,
            size_bytes=len(content),
        )

    def test_copy_verifies_hash_scaffolds_and_keeps_source(self) -> None:
        photo = self.make("JB000001.ARW", b"raw-bytes")
        clip = self.make("C0001.MP4", b"video", folder="PRIVATE/M4ROOT/CLIP")
        records = transfer_files(
            [photo, clip], self.shoot_dir, self.ledger, "card", has_video=True
        )
        self.assertEqual([record.status for record in records], ["copied", "copied"])
        self.assertEqual(records[0].sha256, hashlib.sha256(b"raw-bytes").hexdigest())
        self.assertEqual(
            (self.shoot_dir / "Photo" / "RAW" / "JB000001.ARW").read_bytes(), b"raw-bytes"
        )
        self.assertTrue((self.shoot_dir / "Video" / "RAW" / "C0001.MP4").is_file())
        for folder in ("Photo/Exports", "Video/Exports"):
            self.assertTrue((self.shoot_dir / folder).is_dir())
        self.assertTrue(photo.source.is_file(), "card files must never be removed")
        self.assertEqual(list(self.shoot_dir.rglob(".*.partial")), [])

    def test_photo_only_shoot_has_no_video_folder(self) -> None:
        photo = self.make("JB000001.ARW", b"raw")
        transfer_files([photo], self.shoot_dir, self.ledger, "card", has_video=False)
        self.assertFalse((self.shoot_dir / "Video").exists())

    def test_ledger_makes_reinsert_a_noop(self) -> None:
        photo = self.make("JB000001.ARW", b"raw")
        transfer_files([photo], self.shoot_dir, self.ledger, "card", has_video=False)
        new, already = filter_new([photo], self.ledger.known_keys())
        self.assertEqual((new, already), ([], [photo]))
        self.assertEqual(len(self.ledger.path.read_text().splitlines()), 1)

    def test_identical_existing_file_is_already_present(self) -> None:
        photo = self.make("JB000001.ARW", b"same")
        target = self.shoot_dir / "Photo" / "RAW" / "JB000001.ARW"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"same")
        (record,) = transfer_files([photo], self.shoot_dir, self.ledger, "card", has_video=False)
        self.assertEqual(record.status, "already_present")

    def test_same_name_different_content_is_refused(self) -> None:
        photo = self.make("JB000001.ARW", b"card")
        target = self.shoot_dir / "Photo" / "RAW" / "JB000001.ARW"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"ssd!")
        with self.assertRaises(CollisionError):
            copy_verified(photo.source, target)
        self.assertEqual(target.read_bytes(), b"ssd!")
        self.assertEqual(list(target.parent.glob(".*.partial")), [])

    def test_size_mismatch_is_refused_before_any_copy(self) -> None:
        first = self.make("JB000001.ARW", b"one")
        second = self.make("JB000002.ARW", b"two")
        target = self.shoot_dir / "Photo" / "RAW" / "JB000002.ARW"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"longer content")
        with self.assertRaises(CollisionError):
            transfer_files([first, second], self.shoot_dir, self.ledger, "card", has_video=False)
        self.assertFalse((self.shoot_dir / "Photo" / "RAW" / "JB000001.ARW").exists())
        self.assertEqual(self.ledger.known_keys(), set())

    def test_duplicate_names_on_card_are_refused(self) -> None:
        first = self.make("JB000001.ARW", b"one", folder="DCIM/100MSDCF")
        second = self.make("JB000001.ARW", b"two", folder="DCIM/101MSDCF")
        with self.assertRaises(CollisionError):
            transfer_files([first, second], self.shoot_dir, self.ledger, "card", has_video=False)


if __name__ == "__main__":
    unittest.main()
