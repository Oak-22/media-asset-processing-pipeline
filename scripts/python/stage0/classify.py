"""Suggest a taxonomy category for a shoot from on-device Apple Vision labels.

Vision output is treated as ranked suggestions only. The operator confirms
the category in the Stage 0 questionnaire unless the evidence clears the
configured auto-accept threshold for a category that is not always asked.

Run directly to print labels and candidates for image files:

    python3 scripts/python/stage0/classify.py path/to/*.jpg
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.python.stage0.config import DEFAULT_CONFIG_PATH, ClassificationConfig, load_config
from scripts.python.stage0.inventory import CardFile, Shoot, resolve_exiftool


VISION_READABLE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".hif", ".heif", ".heic", ".png"})
PREVIEW_TAGS = ("-PreviewImage", "-JpgFromRaw", "-ThumbnailImage")
TOP_LABEL_COUNT = 10

Geocoder = Callable[[float, float], str | None]


class ClassifierUnavailable(RuntimeError):
    """Raised when the Vision framework bindings cannot be loaded."""


@dataclass(frozen=True)
class FrameAnalysis:
    """Vision output for one sampled frame."""

    labels: dict[str, float]
    face_count: int
    human_count: int


class ImageAnalyzer(Protocol):
    """Interface for per-frame image analysis; tests inject fakes."""

    name: str

    def analyze(self, image_path: Path) -> FrameAnalysis: ...


@dataclass(frozen=True)
class AggregateSignals:
    """Per-shoot aggregate of sampled frame analyses."""

    frame_count: int
    label_means: dict[str, float]
    face_frame_ratio: float
    human_frame_ratio: float
    person_frame_ratio: float


@dataclass(frozen=True)
class CategoryCandidate:
    """One ranked taxonomy suggestion."""

    category: str
    evidence: float
    confidence: float
    supporting_labels: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "category": self.category,
            "confidence": round(self.confidence, 4),
            "evidence": round(self.evidence, 4),
            "supporting_labels": list(self.supporting_labels),
        }


@dataclass(frozen=True)
class ShootClassification:
    """Classifier suggestions for a shoot, recorded as suggestions."""

    classifier: str
    frames_sampled: int
    candidates: tuple[CategoryCandidate, ...]
    auto_accepted_category: str | None
    top_labels: tuple[tuple[str, float], ...]
    face_frame_ratio: float
    human_frame_ratio: float
    location_suggestion: str | None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_record(self) -> dict[str, object]:
        return {
            "classifier": self.classifier,
            "frames_sampled": self.frames_sampled,
            "auto_accepted_category": self.auto_accepted_category,
            "candidates": [candidate.to_record() for candidate in self.candidates],
            "top_labels": [
                {"label": label, "mean_confidence": round(score, 4)}
                for label, score in self.top_labels
            ],
            "face_frame_ratio": round(self.face_frame_ratio, 4),
            "human_frame_ratio": round(self.human_frame_ratio, 4),
            "location_suggestion": self.location_suggestion,
            "notes": list(self.notes),
        }


class VisionAnalyzer:
    """Apple Vision classification plus face and human rectangle detection."""

    name = "apple_vision"

    def __init__(self) -> None:
        try:
            import Foundation
            import objc
            import Vision
        except ImportError as exc:
            raise ClassifierUnavailable(
                "Apple Vision bindings are not installed. Run "
                "`pip install -r scripts/python/stage0/requirements.txt` in the repo .venv."
            ) from exc
        self._foundation = Foundation
        self._objc = objc
        self._vision = Vision

    def analyze(self, image_path: Path) -> FrameAnalysis:
        vision = self._vision
        with self._objc.autorelease_pool():
            url = self._foundation.NSURL.fileURLWithPath_(str(image_path))
            handler = vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
            classify = vision.VNClassifyImageRequest.alloc().init()
            faces = vision.VNDetectFaceRectanglesRequest.alloc().init()
            humans = vision.VNDetectHumanRectanglesRequest.alloc().init()
            ok, error = handler.performRequests_error_([classify, faces, humans], None)
            if not ok:
                raise RuntimeError(f"Vision failed on {image_path}: {error}")
            labels = {
                str(observation.identifier()): float(observation.confidence())
                for observation in classify.results() or []
            }
            return FrameAnalysis(
                labels=labels,
                face_count=len(faces.results() or []),
                human_count=len(humans.results() or []),
            )


def reverse_geocode(latitude: float, longitude: float, timeout: float = 10.0) -> str | None:
    """Return "City, Region" for a GPS fix via CLGeocoder, or None."""
    try:
        import CoreLocation
        import Foundation
    except ImportError:
        return None
    result: dict[str, object] = {}

    def handler(placemarks: object, error: object) -> None:
        result["placemarks"] = placemarks
        result["error"] = error
        result["done"] = True

    geocoder = CoreLocation.CLGeocoder.alloc().init()
    location = CoreLocation.CLLocation.alloc().initWithLatitude_longitude_(latitude, longitude)
    geocoder.reverseGeocodeLocation_completionHandler_(location, handler)
    deadline = time.monotonic() + timeout
    run_loop = Foundation.NSRunLoop.currentRunLoop()
    while not result.get("done") and time.monotonic() < deadline:
        run_loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))
    if not result.get("done"):
        geocoder.cancelGeocode()
        return None
    placemarks = result.get("placemarks")
    if not placemarks:
        return None
    placemark = placemarks[0]
    parts = [part for part in (placemark.locality(), placemark.administrativeArea()) if part]
    if parts:
        return ", ".join(str(part) for part in parts)
    name = placemark.name()
    return str(name) if name else None


def sample_frames(files: Sequence[CardFile], sample_size: int) -> list[CardFile]:
    """Pick up to `sample_size` evenly spaced photos, one per capture stem."""
    by_stem: dict[tuple[Path, str], CardFile] = {}
    for item in files:
        if item.media != "photo" or item.role != "primary":
            continue
        key = (item.source.parent, item.source.stem.lower())
        current = by_stem.get(key)
        # Prefer a camera JPEG over RAW: Vision reads it without preview extraction.
        if current is None or item.source.suffix.lower() in VISION_READABLE_EXTENSIONS:
            by_stem[key] = item
    photos = sorted(by_stem.values(), key=lambda item: (item.capture_time, str(item.source)))
    if sample_size <= 0 or not photos:
        return []
    if len(photos) <= sample_size:
        return photos
    if sample_size == 1:
        return [photos[len(photos) // 2]]
    step = (len(photos) - 1) / (sample_size - 1)
    indexes = sorted({round(index * step) for index in range(sample_size)})
    return [photos[index] for index in indexes]


def extract_preview(image_path: Path, work_dir: Path, exiftool: str) -> Path | None:
    """Return a Vision-readable image: the file itself or its embedded JPEG preview."""
    if image_path.suffix.lower() in VISION_READABLE_EXTENSIONS:
        return image_path
    for tag in PREVIEW_TAGS:
        completed = subprocess.run(
            [exiftool, "-b", tag, str(image_path)],
            capture_output=True,
            check=False,
        )
        if completed.stdout[:2] == b"\xff\xd8":
            target = work_dir / f"{image_path.stem}{tag.lstrip('-')}.jpg"
            target.write_bytes(completed.stdout)
            return target
    return None


def aggregate(analyses: Sequence[FrameAnalysis]) -> AggregateSignals:
    """Average label confidences and count frames with faces or humans."""
    if not analyses:
        return AggregateSignals(0, {}, 0.0, 0.0, 0.0)
    totals: dict[str, float] = {}
    for analysis in analyses:
        for label, confidence in analysis.labels.items():
            totals[label] = totals.get(label, 0.0) + confidence
    count = len(analyses)
    return AggregateSignals(
        frame_count=count,
        label_means={label: total / count for label, total in totals.items()},
        face_frame_ratio=sum(1 for item in analyses if item.face_count) / count,
        human_frame_ratio=sum(1 for item in analyses if item.human_count) / count,
        person_frame_ratio=sum(
            1 for item in analyses if item.face_count or item.human_count
        ) / count,
    )


def score_categories(
    signals: AggregateSignals,
    config: ClassificationConfig,
) -> list[CategoryCandidate]:
    """Rank taxonomy categories from aggregated Vision signals.

    Category evidence is the strongest mapped label mean above the noise
    floor; the People category also considers the weighted share of frames
    with a detected face or human.
    Confidence is each category's share of total evidence.
    """
    raw: list[tuple[str, float, tuple[str, ...]]] = []
    for category, labels in config.label_map.items():
        matched = sorted(
            (
                (label, signals.label_means[label])
                for label in labels
                if signals.label_means.get(label, 0.0) >= config.label_floor
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        evidence = matched[0][1] if matched else 0.0
        supporting = [label for label, _score in matched[:3]]
        if category == config.people_category:
            person_signal = config.people_signal_weight * signals.person_frame_ratio
            if person_signal > evidence:
                evidence = person_signal
            if person_signal > 0:
                supporting.append("faces_or_humans_detected")
        if evidence > 0:
            raw.append((category, evidence, tuple(supporting)))
    total = sum(evidence for _category, evidence, _labels in raw)
    candidates = [
        CategoryCandidate(category, evidence, evidence / total, labels)
        for category, evidence, labels in raw
    ]
    return sorted(candidates, key=lambda item: (-item.evidence, item.category))


def auto_accept(candidates: Sequence[CategoryCandidate], config: ClassificationConfig) -> str | None:
    """Return the top category when it may skip the category dialog."""
    if not candidates:
        return None
    top = candidates[0]
    if top.category in config.always_ask_categories:
        return None
    if top.confidence >= config.auto_accept_confidence and top.evidence >= config.min_evidence:
        return top.category
    return None


def classify_images(
    images: Sequence[Path],
    analyzer: ImageAnalyzer,
) -> tuple[list[FrameAnalysis], list[str]]:
    """Analyze images, collecting per-frame failures as notes."""
    analyses: list[FrameAnalysis] = []
    notes: list[str] = []
    for image in images:
        try:
            analyses.append(analyzer.analyze(image))
        except Exception as exc:  # noqa: BLE001 - one bad frame must not stop the offload
            notes.append(f"frame skipped: {image.name}: {exc}")
    return analyses, notes


def classify_shoot(
    shoot: Shoot,
    analyzer: ImageAnalyzer | None,
    config: ClassificationConfig,
    exiftool: str,
    geocoder: Geocoder | None = None,
) -> ShootClassification:
    """Sample frames, run Vision, and rank taxonomy suggestions for a shoot."""
    notes: list[str] = []
    analyses: list[FrameAnalysis] = []
    if analyzer is None:
        notes.append("classifier unavailable; category must be chosen by the operator")
    else:
        with tempfile.TemporaryDirectory(prefix="stage0-previews-") as tmp:
            work_dir = Path(tmp)
            images: list[Path] = []
            for item in sample_frames(shoot.files, config.sample_size):
                preview = extract_preview(item.source, work_dir, exiftool)
                if preview is None:
                    notes.append(f"no preview: {item.source.name}")
                else:
                    images.append(preview)
            analyses, frame_notes = classify_images(images, analyzer)
            notes.extend(frame_notes)

    signals = aggregate(analyses)
    candidates = score_categories(signals, config)
    location = None
    if geocoder is not None and shoot.gps is not None:
        try:
            location = geocoder(*shoot.gps)
        except Exception as exc:  # noqa: BLE001 - location is optional
            notes.append(f"reverse geocode failed: {exc}")
    top_labels = sorted(signals.label_means.items(), key=lambda pair: pair[1], reverse=True)
    return ShootClassification(
        classifier=analyzer.name if analyzer else "none",
        frames_sampled=signals.frame_count,
        candidates=tuple(candidates),
        auto_accepted_category=auto_accept(candidates, config),
        top_labels=tuple(top_labels[:TOP_LABEL_COUNT]),
        face_frame_ratio=signals.face_frame_ratio,
        human_frame_ratio=signals.human_frame_ratio,
        location_suggestion=location,
        notes=tuple(notes),
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the classifier sanity check."""
    parser = argparse.ArgumentParser(
        description="Print Apple Vision labels and taxonomy candidates for images."
    )
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    return parser.parse_args()


def main() -> None:
    """Classify each image, then the set as one shoot."""
    args = parse_args()
    config = load_config(args.config)
    try:
        analyzer = VisionAnalyzer()
    except ClassifierUnavailable as exc:
        raise SystemExit(str(exc)) from exc
    exiftool = resolve_exiftool(config.exiftool_path)
    analyses: list[FrameAnalysis] = []
    with tempfile.TemporaryDirectory(prefix="stage0-previews-") as tmp:
        for image in args.images:
            preview = extract_preview(image, Path(tmp), exiftool)
            if preview is None:
                print(f"{image.name}: no readable preview")
                continue
            analysis = analyzer.analyze(preview)
            analyses.append(analysis)
            top = sorted(analysis.labels.items(), key=lambda pair: pair[1], reverse=True)[:5]
            labels = ", ".join(f"{label} {score:.2f}" for label, score in top)
            print(
                f"{image.name}: faces={analysis.face_count} "
                f"humans={analysis.human_count} | {labels}"
            )
    candidates = score_categories(aggregate(analyses), config.classification)
    print("\nShoot-level candidates:")
    for candidate in candidates[:3]:
        print(
            f"  {candidate.category}: confidence {candidate.confidence:.2f} "
            f"(evidence {candidate.evidence:.2f}; {', '.join(candidate.supporting_labels)})"
        )
    accepted = auto_accept(candidates, config.classification)
    print(f"Auto-accepted category: {accepted or 'none (operator asked)'}")


if __name__ == "__main__":
    main()
