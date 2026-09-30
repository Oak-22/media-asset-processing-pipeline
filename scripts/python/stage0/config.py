"""Load and validate the Stage 0 offload configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "stage0_offload.toml"

REQUIRED_QUESTIONS = (
    "category",
    "category_all",
    "people_branch",
    "subcategory",
    "new_folder",
    "shoot_folder",
    "subject",
    "client",
    "session",
    "descriptor",
    "location",
    "confirm",
    "merge",
)
REQUIRED_OPTIONS = (
    "other_category",
    "file_here",
    "new_folder",
    "new_shoot",
    "new_client_session",
    "existing_prefix",
    "merge",
    "inbox",
)


@dataclass(frozen=True)
class ClassificationConfig:
    """Classifier sampling, scoring, and auto-accept settings."""

    sample_size: int = 12
    auto_accept_confidence: float = 0.6
    min_evidence: float = 0.25
    label_floor: float = 0.15
    people_category: str = "People"
    people_signal_weight: float = 0.6
    always_ask_categories: tuple[str, ...] = ("People",)
    reverse_geocode: bool = True
    geocode_timeout_seconds: float = 10.0
    label_map: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class DialogConfig:
    """Operator-facing dialog text, kept in config so it can change without code."""

    title: str
    timeout_seconds: int
    questions: dict[str, str]
    options: dict[str, str]


@dataclass(frozen=True)
class OffloadConfig:
    """Validated Stage 0 configuration."""

    source_path: Path
    ssd_volume_uuid: str
    ssd_display_name: str
    photo_root: str
    inbox_folder: str
    state_dir: Path
    manifest_dir: str
    exiftool_path: str | None
    gap_hours: float
    split_on_date_change: bool
    max_depth: int
    classification: ClassificationConfig
    dialogs: DialogConfig


def _section(data: dict[str, object], name: str, path: Path) -> dict[str, object]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise SystemExit(f"Config {path} is missing the [{name}] table.")
    return value


def _require_keys(table: dict[str, object], keys: tuple[str, ...], label: str, path: Path) -> None:
    missing = [key for key in keys if not isinstance(table.get(key), str)]
    if missing:
        raise SystemExit(f"Config {path} [{label}] is missing: {', '.join(missing)}")


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> OffloadConfig:
    """Read the TOML config and return a validated OffloadConfig."""
    config_path = Path(path)
    if not config_path.is_file():
        raise SystemExit(f"Stage 0 config not found: {config_path}")
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    volumes = _section(data, "volumes", config_path)
    segmentation = _section(data, "segmentation", config_path)
    classification = _section(data, "classification", config_path)
    taxonomy = _section(data, "taxonomy", config_path)
    dialogs = _section(data, "dialogs", config_path)
    state = _section(data, "state", config_path)

    label_map_raw = taxonomy.get("label_map", {})
    if not isinstance(label_map_raw, dict) or not label_map_raw:
        raise SystemExit(f"Config {config_path} [taxonomy.label_map] must map categories to labels.")
    label_map = {
        str(category): tuple(str(label) for label in labels)
        for category, labels in label_map_raw.items()
    }

    questions = dialogs.get("questions", {})
    options = dialogs.get("options", {})
    if not isinstance(questions, dict) or not isinstance(options, dict):
        raise SystemExit(f"Config {config_path} needs [dialogs.questions] and [dialogs.options].")
    _require_keys(questions, REQUIRED_QUESTIONS, "dialogs.questions", config_path)
    _require_keys(options, REQUIRED_OPTIONS, "dialogs.options", config_path)

    ssd_uuid = volumes.get("ssd_volume_uuid")
    if not isinstance(ssd_uuid, str) or not ssd_uuid:
        raise SystemExit(f"Config {config_path} [volumes] needs ssd_volume_uuid.")

    exiftool_path = volumes.get("exiftool_path") or None

    return OffloadConfig(
        source_path=config_path,
        ssd_volume_uuid=ssd_uuid.upper(),
        ssd_display_name=str(volumes.get("ssd_display_name", "destination SSD")),
        photo_root=str(volumes.get("photo_root", "JB Photography")),
        inbox_folder=str(volumes.get("inbox_folder", "_Inbox")),
        state_dir=Path(str(state.get("state_dir", "~/.jbphoto-offload"))).expanduser(),
        manifest_dir=str(state.get("manifest_dir", "outputs/stage0/offloads")),
        exiftool_path=str(exiftool_path) if exiftool_path else None,
        gap_hours=float(segmentation.get("gap_hours", 3.0)),
        split_on_date_change=bool(segmentation.get("split_on_date_change", True)),
        max_depth=int(taxonomy.get("max_depth", 6)),
        classification=ClassificationConfig(
            sample_size=int(classification.get("sample_size", 12)),
            auto_accept_confidence=float(classification.get("auto_accept_confidence", 0.6)),
            min_evidence=float(classification.get("min_evidence", 0.25)),
            label_floor=float(classification.get("label_floor", 0.15)),
            people_category=str(classification.get("people_category", "People")),
            people_signal_weight=float(classification.get("people_signal_weight", 0.6)),
            always_ask_categories=tuple(
                str(item) for item in classification.get("always_ask_categories", ["People"])
            ),
            reverse_geocode=bool(classification.get("reverse_geocode", True)),
            geocode_timeout_seconds=float(classification.get("geocode_timeout_seconds", 10.0)),
            label_map=label_map,
        ),
        dialogs=DialogConfig(
            title=str(dialogs.get("title", "SD Offload")),
            timeout_seconds=int(dialogs.get("timeout_seconds", 1800)),
            questions={str(key): str(value) for key, value in questions.items()},
            options={str(key): str(value) for key, value in options.items()},
        ),
    )
