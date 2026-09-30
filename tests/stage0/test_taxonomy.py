"""Tests for Stage 0 taxonomy reading and folder naming."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path, PurePosixPath

from scripts.python.stage0.taxonomy import (
    TaxonomyReader,
    build_tree,
    inbox_relpath,
    parse_relpath,
    repeat_client_relpath,
    sanitize_component,
    shoot_folder_name,
)


def make_dirs(root: Path, *relpaths: str) -> None:
    for relpath in relpaths:
        (root / relpath).mkdir(parents=True, exist_ok=True)


class TaxonomyTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_dirs(
            self.root,
            "Animals",
            "Automotive/Nascar – Sonoma, CA/RAW/Photo",
            "People/Personal/Family",
            "People/Client Work — SSD/Commercial/Brand Photography/DJ Alx/Mangos 2026/Photo/RAW",
            "People/Client Work — SSD/Events/Education/Graduation — SSD/High School/Melliah Davis/Photo/RAW",
            "JB Catalog Previews.lrdata/0",
            "__LrC Catalog Archive/2025",
            ".Spotlight-V100",
            "_Inbox/2026-05-10 – Unsorted/Photo/RAW",
        )
        (self.root / "Landscape").mkdir()
        (self.root / "Landscape" / "Legacy Shoot").mkdir()
        (self.root / "Landscape" / "Legacy Shoot" / "JB000001.ARW").write_bytes(b"x")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_top_level_ignores_catalog_artifacts_dotfiles_and_inbox(self) -> None:
        reader = TaxonomyReader(self.root, frozenset({"_Inbox"}))
        listing = reader.listing(PurePosixPath())
        self.assertEqual(listing.subfolders, ("Animals", "Automotive", "Landscape", "People"))
        self.assertEqual(listing.shoot_folders, ())

    def test_shoot_folders_are_separated_from_subfolders(self) -> None:
        reader = TaxonomyReader(self.root)
        self.assertEqual(
            reader.listing(PurePosixPath("Automotive")).shoot_folders, ("Nascar – Sonoma, CA",)
        )
        self.assertEqual(
            reader.listing(PurePosixPath("Landscape")).shoot_folders, ("Legacy Shoot",)
        )
        dj = PurePosixPath("People/Client Work — SSD/Commercial/Brand Photography/DJ Alx")
        self.assertEqual(reader.listing(dj).shoot_folders, ("Mangos 2026",))

    def test_build_tree_stops_at_shoot_folders(self) -> None:
        tree = build_tree(TaxonomyReader(self.root, frozenset({"_Inbox"})))
        people = tree["People"]
        assert isinstance(people, dict)
        self.assertEqual(sorted(people), ["Client Work — SSD", "Personal"])
        events = people["Client Work — SSD"]["Events"]["Education"]["Graduation — SSD"]
        self.assertEqual(events, {"High School": {"Melliah Davis": None}})
        self.assertIsNone(tree["Automotive"]["Nascar – Sonoma, CA"])

    def test_missing_folder_lists_empty(self) -> None:
        listing = TaxonomyReader(self.root).listing(PurePosixPath("Nope/Deeper"))
        self.assertEqual((listing.subfolders, listing.shoot_folders), ((), ()))


class FolderNameTest(unittest.TestCase):
    def test_uses_en_dash_and_skips_empty_parts(self) -> None:
        self.assertEqual(
            shoot_folder_name("Brandy", "Modeling", "Outdoors"), "Brandy – Modeling – Outdoors"
        )
        self.assertEqual(shoot_folder_name("Nascar", "", "Sonoma, CA"), "Nascar – Sonoma, CA")
        self.assertEqual(shoot_folder_name("  Lake Tahoe ", "  "), "Lake Tahoe")
        self.assertIn("–", shoot_folder_name("A", "B"))

    def test_special_characters_are_cleaned(self) -> None:
        self.assertEqual(sanitize_component("AC/DC: Live"), "AC-DC- Live")
        self.assertEqual(sanitize_component("..hidden. "), "hidden")
        self.assertEqual(sanitize_component("O'Brien & Sons"), "O'Brien & Sons")
        self.assertEqual(sanitize_component("Tab\tand\nnewline"), "Tab and newline")
        with self.assertRaises(ValueError):
            sanitize_component("   ")
        with self.assertRaises(ValueError):
            sanitize_component("..")

    def test_repeat_client_form(self) -> None:
        self.assertEqual(
            repeat_client_relpath("DJ Alx", "Mangos", 2026), PurePosixPath("DJ Alx/Mangos 2026")
        )
        self.assertEqual(
            repeat_client_relpath("DJ Alx", "Mangos 2026", 2026),
            PurePosixPath("DJ Alx/Mangos 2026"),
        )

    def test_inbox_and_edited_paths(self) -> None:
        self.assertEqual(
            inbox_relpath("_Inbox", date(2026, 5, 10)),
            PurePosixPath("_Inbox/2026-05-10 – Unsorted"),
        )
        self.assertEqual(
            parse_relpath("/People/Personal//Family/ Brandy – Modeling /"),
            PurePosixPath("People/Personal/Family/Brandy – Modeling"),
        )
        with self.assertRaises(ValueError):
            parse_relpath("People/../Secrets")
        with self.assertRaises(ValueError):
            parse_relpath("   ")


if __name__ == "__main__":
    unittest.main()
