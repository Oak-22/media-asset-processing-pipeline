"""Tests for Stage 0 label aggregation and taxonomy scoring with fake Vision."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path

from scripts.python.stage0.classify import (
    FrameAnalysis,
    aggregate,
    auto_accept,
    classify_shoot,
    sample_frames,
    score_categories,
)
from scripts.python.stage0.config import ClassificationConfig
from scripts.python.stage0.inventory import Shoot

from .helpers import card_file


CONFIG = ClassificationConfig(
    auto_accept_confidence=0.6,
    min_evidence=0.25,
    label_floor=0.15,
    label_map={
        "Automotive": ("automobile", "car", "motorsport"),
        "Landscape": ("mountain", "lake", "sunset_sunrise"),
        "People": ("people", "adult"),
    },
)


class FakeAnalyzer:
    """Returns canned analyses in order and records the paths it saw."""

    name = "fake_vision"

    def __init__(self, analyses: list[FrameAnalysis]) -> None:
        self.analyses = list(analyses)
        self.seen: list[Path] = []

    def analyze(self, image_path: Path) -> FrameAnalysis:
        self.seen.append(image_path)
        return self.analyses[(len(self.seen) - 1) % len(self.analyses)]


def frame(labels: dict[str, float], faces: int = 0, humans: int = 0) -> FrameAnalysis:
    return FrameAnalysis(labels=labels, face_count=faces, human_count=humans)


class ScoringTest(unittest.TestCase):
    def test_landscape_shoot_is_auto_accepted(self) -> None:
        signals = aggregate(
            [
                frame({"mountain": 0.9, "lake": 0.6, "car": 0.1}),
                frame({"mountain": 0.8, "sunset_sunrise": 0.7}),
            ]
        )
        candidates = score_categories(signals, CONFIG)
        self.assertEqual([candidate.category for candidate in candidates], ["Landscape"])
        self.assertAlmostEqual(candidates[0].evidence, 0.85)
        self.assertEqual(candidates[0].supporting_labels[0], "mountain")
        self.assertEqual(auto_accept(candidates, CONFIG), "Landscape")

    def test_people_is_never_auto_accepted(self) -> None:
        signals = aggregate([frame({"people": 0.95}, faces=2), frame({"adult": 0.9}, faces=1)])
        candidates = score_categories(signals, CONFIG)
        self.assertEqual(candidates[0].category, "People")
        self.assertIn("faces_or_humans_detected", candidates[0].supporting_labels)
        self.assertIsNone(auto_accept(candidates, CONFIG))

    def test_faces_alone_create_people_evidence(self) -> None:
        signals = aggregate([frame({}, faces=1), frame({}, humans=1)])
        (candidate,) = score_categories(signals, CONFIG)
        self.assertEqual(candidate.category, "People")
        self.assertAlmostEqual(candidate.evidence, CONFIG.people_signal_weight)

    def test_bystanders_do_not_outrank_strong_object_labels(self) -> None:
        signals = aggregate([frame({"car": 0.9}, humans=2), frame({"car": 0.85}, faces=1)])
        candidates = score_categories(signals, CONFIG)
        self.assertEqual([c.category for c in candidates], ["Automotive", "People"])

    def test_ambiguous_shoot_asks_the_operator(self) -> None:
        signals = aggregate([frame({"car": 0.7, "mountain": 0.6})])
        candidates = score_categories(signals, CONFIG)
        self.assertEqual([candidate.category for candidate in candidates], ["Automotive", "Landscape"])
        self.assertAlmostEqual(sum(candidate.confidence for candidate in candidates), 1.0)
        self.assertIsNone(auto_accept(candidates, CONFIG))

    def test_labels_below_floor_are_noise(self) -> None:
        signals = aggregate([frame({"car": 0.1, "mountain": 0.05})])
        self.assertEqual(score_categories(signals, CONFIG), [])
        self.assertIsNone(auto_accept([], CONFIG))


class ShootClassificationTest(unittest.TestCase):
    def test_sampling_prefers_camera_jpeg_and_spreads_frames(self) -> None:
        start = datetime(2026, 5, 10, 9, 0)
        files = []
        for index in range(30):
            moment = start + timedelta(minutes=index)
            files.append(card_file(f"JB{index:06d}.ARW", moment))
            files.append(card_file(f"JB{index:06d}.JPG", moment))
        sampled = sample_frames(files, 12)
        self.assertEqual(len(sampled), 12)
        self.assertTrue(all(item.source.suffix == ".JPG" for item in sampled))
        self.assertEqual(sampled[0].source.name, "JB000000.JPG")
        self.assertEqual(sampled[-1].source.name, "JB000029.JPG")

    def test_classify_shoot_with_fake_vision_and_geocoder(self) -> None:
        start = datetime(2026, 5, 10, 9, 0)
        files = tuple(
            card_file(f"JB{index:06d}.JPG", start + timedelta(minutes=index), gps=(38.29, -122.46))
            for index in range(5)
        )
        analyzer = FakeAnalyzer([frame({"car": 0.9, "motorsport": 0.8}, humans=1)])
        result = classify_shoot(
            Shoot("2026-05-10_0900", files),
            analyzer,
            CONFIG,
            exiftool="/unused/exiftool",
            geocoder=lambda latitude, longitude: "Sonoma, CA",
        )
        self.assertEqual(len(analyzer.seen), 5)
        self.assertEqual(result.classifier, "fake_vision")
        self.assertEqual(result.candidates[0].category, "Automotive")
        self.assertEqual(result.location_suggestion, "Sonoma, CA")
        record = result.to_record()
        self.assertEqual(record["frames_sampled"], 5)
        self.assertEqual(record["top_labels"][0]["label"], "car")

    def test_missing_classifier_leaves_choice_to_operator(self) -> None:
        files = (card_file("JB000001.JPG", datetime(2026, 5, 10, 9, 0)),)
        result = classify_shoot(Shoot("s", files), None, CONFIG, exiftool="/unused")
        self.assertEqual(result.candidates, ())
        self.assertIsNone(result.auto_accepted_category)
        self.assertTrue(result.notes)


if __name__ == "__main__":
    unittest.main()
