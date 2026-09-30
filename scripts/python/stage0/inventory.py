"""Inventory camera-card files, filter the offload ledger, and segment shoots."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from scripts.python.stage0.volumes import access_denied


PHOTO_EXTENSIONS = frozenset({".arw", ".jpg", ".jpeg", ".hif", ".heif", ".heic", ".dng"})
PHOTO_SIDECAR_EXTENSIONS = frozenset({".xmp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mts", ".m2ts"})
VIDEO_SIDECAR_EXTENSIONS = frozenset({".xml"})
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | PHOTO_SIDECAR_EXTENSIONS | VIDEO_EXTENSIONS | VIDEO_SIDECAR_EXTENSIONS

CARD_SCAN_ROOTS = (PurePosixPath("DCIM"), PurePosixPath("PRIVATE/M4ROOT/CLIP"))
SHOOT_SCAN_ROOTS = (PurePosixPath("Photo/RAW"), PurePosixPath("Video/RAW"))

# Sony clip metadata is named C0001M01.XML next to C0001.MP4.
SONY_CLIP_METADATA = re.compile(r"^(?P<stem>.+)M\d{2}$", re.IGNORECASE)
EXIF_TIME_FORMAT = "%Y:%m:%d %H:%M:%S"
EXIFTOOL_FALLBACKS = ("/opt/homebrew/bin/exiftool", "/usr/local/bin/exiftool")
EXIFTOOL_TAGS = (
    "-DateTimeOriginal",
    "-CreateDate",
    "-FileModifyDate",
    "-Model",
    "-Composite:GPSLatitude",
    "-Composite:GPSLongitude",
    "-FileType",
)

MetadataReader = Callable[[Sequence[Path]], dict[str, dict[str, object]]]


@dataclass(frozen=True)
class CardFile:
    """One media file found on the card, with the metadata Stage 0 uses."""

    source: Path
    relative_path: PurePosixPath
    media: str
    role: str
    size_bytes: int
    capture_time: datetime
    capture_time_source: str
    camera_model: str | None = None
    gps: tuple[float, float] | None = None

    @property
    def identity_key(self) -> str:
        """Key used by the offload ledger to recognise a file on reinsert."""
        return f"{self.source.name}|{self.size_bytes}|{self.capture_time.isoformat()}"


@dataclass(frozen=True)
class Shoot:
    """A capture-time segment of card files that is filed as one unit."""

    shoot_id: str
    files: tuple[CardFile, ...]

    @property
    def start(self) -> datetime:
        return self.files[0].capture_time

    @property
    def end(self) -> datetime:
        return self.files[-1].capture_time

    @property
    def photo_count(self) -> int:
        return sum(1 for item in self.files if item.media == "photo" and item.role == "primary")

    @property
    def video_count(self) -> int:
        return sum(1 for item in self.files if item.media == "video" and item.role == "primary")

    @property
    def has_video(self) -> bool:
        return any(item.media == "video" for item in self.files)

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)

    @property
    def gps(self) -> tuple[float, float] | None:
        """Return the first GPS fix in the shoot, if any."""
        return next((item.gps for item in self.files if item.gps), None)


def media_kind(path: Path | PurePosixPath) -> tuple[str, str] | None:
    """Return (media, role) for a card file, or None when it is not offloaded."""
    suffix = path.suffix.lower()
    if suffix in PHOTO_EXTENSIONS:
        return ("photo", "primary")
    if suffix in PHOTO_SIDECAR_EXTENSIONS:
        return ("photo", "sidecar")
    if suffix in VIDEO_EXTENSIONS:
        return ("video", "primary")
    if suffix in VIDEO_SIDECAR_EXTENSIONS:
        return ("video", "sidecar")
    return None


def pairing_stem(path: Path | PurePosixPath) -> str:
    """Return the stem that links sidecars to their primary file."""
    stem = path.stem
    if path.suffix.lower() in VIDEO_SIDECAR_EXTENSIONS:
        match = SONY_CLIP_METADATA.match(stem)
        if match:
            stem = match.group("stem")
    return stem.lower()


def scan_media(root: Path, scan_roots: Iterable[PurePosixPath] = CARD_SCAN_ROOTS) -> list[Path]:
    """Return offloadable media files under the given roots, skipping dotfiles."""
    found: list[Path] = []
    for scan_root in scan_roots:
        base = root / scan_root
        if not base.is_dir():
            continue
        try:
            for path in base.rglob("*"):
                if any(part.startswith(".") for part in path.relative_to(root).parts):
                    continue
                if path.is_file() and media_kind(path) is not None:
                    found.append(path)
        except PermissionError as exc:
            raise access_denied(base) from exc
    return sorted(found)


def resolve_exiftool(configured: str | None = None) -> str:
    """Return a usable exiftool path; launchd agents do not inherit Homebrew PATH."""
    candidates = [configured] if configured else []
    which = shutil.which("exiftool")
    if which:
        candidates.append(which)
    candidates.extend(EXIFTOOL_FALLBACKS)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit(
        "exiftool not found. Install it with `brew install exiftool` or set "
        "volumes.exiftool_path in scripts/python/stage0/config/stage0_offload.toml."
    )


def exiftool_reader(exiftool: str) -> MetadataReader:
    """Return a metadata reader that runs exiftool -json over a file list."""

    def read(paths: Sequence[Path]) -> dict[str, dict[str, object]]:
        if not paths:
            return {}
        command = [
            exiftool,
            "-json",
            "-n",
            "-charset",
            "filename=utf8",
            "-api",
            "QuickTimeUTC=1",
            "-api",
            "LargeFileSupport=1",
            *EXIFTOOL_TAGS,
            "-@",
            "-",
        ]
        completed = subprocess.run(
            command,
            input="\n".join(str(path) for path in paths).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        if not completed.stdout.strip():
            detail = completed.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"exiftool returned no metadata: {detail}")
        records = json.loads(completed.stdout)
        return {str(record.get("SourceFile")): record for record in records}

    return read


def parse_exif_time(value: object) -> datetime | None:
    """Parse an EXIF/QuickTime timestamp as naive local capture time."""
    if not isinstance(value, str) or len(value) < 19:
        return None
    try:
        return datetime.strptime(value[:19], EXIF_TIME_FORMAT)
    except ValueError:
        return None


def _gps(record: dict[str, object]) -> tuple[float, float] | None:
    latitude = record.get("GPSLatitude")
    longitude = record.get("GPSLongitude")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        if latitude or longitude:
            return (float(latitude), float(longitude))
    return None


def build_card_files(
    root: Path,
    paths: Sequence[Path],
    metadata: dict[str, dict[str, object]],
) -> list[CardFile]:
    """Combine scanned paths and metadata into CardFile records.

    Capture time falls back from DateTimeOriginal to CreateDate, then to the
    paired primary file (sidecars), then to FileModifyDate, then to mtime.
    """
    own_times: dict[Path, tuple[datetime, str]] = {}
    for path in paths:
        record = metadata.get(str(path), {})
        original = parse_exif_time(record.get("DateTimeOriginal"))
        created = parse_exif_time(record.get("CreateDate"))
        if original:
            own_times[path] = (original, "exif_datetime_original")
        elif created:
            own_times[path] = (created, "exif_create_date")

    pair_times: dict[tuple[Path, str], datetime] = {}
    for path, (moment, _source) in own_times.items():
        if media_kind(path) and media_kind(path)[1] == "primary":
            pair_times.setdefault((path.parent, pairing_stem(path)), moment)

    files: list[CardFile] = []
    for path in paths:
        kind = media_kind(path)
        if kind is None:
            continue
        record = metadata.get(str(path), {})
        if path in own_times:
            capture_time, source = own_times[path]
        elif (path.parent, pairing_stem(path)) in pair_times:
            capture_time, source = pair_times[(path.parent, pairing_stem(path))], "paired_file"
        elif parsed := parse_exif_time(record.get("FileModifyDate")):
            capture_time, source = parsed, "file_modify_date"
        else:
            capture_time = datetime.fromtimestamp(path.stat().st_mtime)
            source = "filesystem_mtime"
        model = record.get("Model")
        files.append(
            CardFile(
                source=path,
                relative_path=PurePosixPath(path.relative_to(root).as_posix()),
                media=kind[0],
                role=kind[1],
                size_bytes=path.stat().st_size,
                capture_time=capture_time,
                capture_time_source=source,
                camera_model=str(model) if model else None,
                gps=_gps(record),
            )
        )
    return files


def build_inventory(
    root: Path,
    reader: MetadataReader,
    scan_roots: Iterable[PurePosixPath] = CARD_SCAN_ROOTS,
) -> list[CardFile]:
    """Scan `root` and return CardFile records sorted by capture time."""
    paths = scan_media(root, scan_roots)
    files = build_card_files(root, paths, reader(paths))
    return sorted(files, key=lambda item: (item.capture_time, str(item.relative_path)))


def filter_new(
    files: Iterable[CardFile],
    known_keys: set[str],
) -> tuple[list[CardFile], list[CardFile]]:
    """Split files into (new, already offloaded) using ledger identity keys."""
    new: list[CardFile] = []
    already: list[CardFile] = []
    for item in files:
        (already if item.identity_key in known_keys else new).append(item)
    return new, already


def segment_shoots(
    files: Iterable[CardFile],
    gap_hours: float,
    split_on_date_change: bool = True,
) -> list[Shoot]:
    """Split files into shoots at capture-time gaps and (optionally) date changes."""
    ordered = sorted(files, key=lambda item: (item.capture_time, str(item.relative_path)))
    gap = timedelta(hours=gap_hours)
    groups: list[list[CardFile]] = []
    for item in ordered:
        if groups:
            previous = groups[-1][-1].capture_time
            date_changed = split_on_date_change and item.capture_time.date() != previous.date()
            if item.capture_time - previous <= gap and not date_changed:
                groups[-1].append(item)
                continue
        groups.append([item])

    shoots: list[Shoot] = []
    seen_ids: dict[str, int] = {}
    for group in groups:
        base_id = group[0].capture_time.strftime("%Y-%m-%d_%H%M")
        seen_ids[base_id] = seen_ids.get(base_id, 0) + 1
        shoot_id = base_id if seen_ids[base_id] == 1 else f"{base_id}_{seen_ids[base_id]}"
        shoots.append(Shoot(shoot_id=shoot_id, files=tuple(group)))
    return shoots
