"""Scaffold shoot folders, copy with SHA-256 verification, and keep the ledger.

Card files are only ever read. Destination files are never overwritten: a
same-name file with a different hash is a collision error.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts.python.stage0.inventory import CardFile


CHUNK_SIZE = 4 * 1024 * 1024


class CollisionError(RuntimeError):
    """Raised when a destination file exists with different content."""


class VerificationError(RuntimeError):
    """Raised when a copied file does not hash to the source digest."""


@dataclass(frozen=True)
class TransferRecord:
    """Outcome for one file in an offload or refile."""

    file: CardFile
    destination: Path
    sha256: str
    status: str

    def to_record(self) -> dict[str, object]:
        return {
            "source": str(self.file.source),
            "source_relpath": str(self.file.relative_path),
            "destination": str(self.destination),
            "sha256": self.sha256,
            "size_bytes": self.file.size_bytes,
            "capture_time_local": self.file.capture_time.isoformat(),
            "capture_time_source": self.file.capture_time_source,
            "status": self.status,
        }


def sha256_file(path: Path) -> str:
    """Calculate a SHA-256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def destination_for(item: CardFile, shoot_dir: Path) -> Path:
    """Return `<shoot>/Photo/RAW/<name>` or `<shoot>/Video/RAW/<name>`."""
    media_folder = "Video" if item.media == "video" else "Photo"
    return shoot_dir / media_folder / "RAW" / item.source.name


def scaffold_shoot(shoot_dir: Path, has_video: bool) -> list[Path]:
    """Create Photo/{RAW,Exports} and, for video shoots, Video/{RAW,Exports}."""
    folders = [shoot_dir / "Photo" / "RAW", shoot_dir / "Photo" / "Exports"]
    if has_video:
        folders += [shoot_dir / "Video" / "RAW", shoot_dir / "Video" / "Exports"]
    created: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            folder.mkdir(parents=True, exist_ok=True)
            created.append(folder)
    return created


def plan_destinations(files: Sequence[CardFile], shoot_dir: Path) -> list[tuple[CardFile, Path]]:
    """Pair each file with its destination path."""
    return [(item, destination_for(item, shoot_dir)) for item in files]


def preflight_collisions(pairs: Sequence[tuple[CardFile, Path]]) -> list[str]:
    """Return collision problems that can be detected without hashing."""
    problems: list[str] = []
    seen: dict[Path, CardFile] = {}
    for item, destination in pairs:
        if destination in seen:
            problems.append(
                f"{item.relative_path} and {seen[destination].relative_path} "
                f"both map to {destination}"
            )
            continue
        seen[destination] = item
        if destination.exists() and destination.stat().st_size != item.size_bytes:
            problems.append(
                f"{destination} already exists with a different size "
                f"({destination.stat().st_size} vs {item.size_bytes} bytes)"
            )
    return problems


def copy_verified(source: Path, destination: Path) -> tuple[str, str]:
    """Copy one file and verify it; return (status, sha256).

    The source is hashed while it is streamed to a temporary file, the
    temporary file is re-read and compared, and only then renamed into
    place. Metadata is copied with shutil.copystat (as shutil.copy2 does).
    An identical existing destination is reported as `already_present`.
    """
    if destination.exists():
        source_hash = sha256_file(source)
        destination_hash = sha256_file(destination)
        if source_hash != destination_hash:
            raise CollisionError(
                f"{destination} already exists with different content; refusing to overwrite."
            )
        return "already_present", source_hash

    partial = destination.with_name(f".{destination.name}.partial")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as reader, partial.open("wb") as writer:
            for chunk in iter(lambda: reader.read(CHUNK_SIZE), b""):
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        shutil.copystat(source, partial)
        source_hash = digest.hexdigest()
        copied_hash = sha256_file(partial)
        if copied_hash != source_hash:
            raise VerificationError(
                f"Hash mismatch copying {source} -> {destination}: "
                f"{source_hash} != {copied_hash}"
            )
        if destination.exists():
            raise CollisionError(f"{destination} appeared during copy; refusing to overwrite.")
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)
    return "copied", source_hash


def move_verified(source: Path, destination: Path) -> tuple[str, str]:
    """Move one file within a volume (refile); return (status, sha256).

    An identical existing destination leaves the source in place and is
    reported as `already_present`.
    """
    source_hash = sha256_file(source)
    if destination.exists():
        if sha256_file(destination) != source_hash:
            raise CollisionError(
                f"{destination} already exists with different content; refusing to overwrite."
            )
        return "already_present", source_hash
    os.rename(source, destination)
    if sha256_file(destination) != source_hash:
        raise VerificationError(f"Hash mismatch after moving {source} -> {destination}")
    return "moved", source_hash


class OffloadLedger:
    """Append-only JSONL record of offloaded files, used for reinsert no-ops."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def known_keys(self) -> set[str]:
        if not self.path.is_file():
            return set()
        keys: set[str] = set()
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(
                        f"Offload ledger {self.path} line {line_number} is not valid JSON: {exc}"
                    ) from exc
                key = entry.get("identity_key")
                if isinstance(key, str):
                    keys.add(key)
        return keys

    def append(self, entries: Iterable[dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def ledger_entry(record: TransferRecord, event: str, source_label: str) -> dict[str, object]:
    """Return one ledger line for a transfer record."""
    return {
        "identity_key": record.file.identity_key,
        "event": event,
        "recorded_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_label": source_label,
        "source_relpath": str(record.file.relative_path),
        "destination": str(record.destination),
        "sha256": record.sha256,
        "size_bytes": record.file.size_bytes,
        "status": record.status,
    }


FileOperation = Callable[[Path, Path], tuple[str, str]]


def transfer_files(
    files: Sequence[CardFile],
    shoot_dir: Path,
    ledger: OffloadLedger,
    source_label: str,
    has_video: bool,
    operation: FileOperation = copy_verified,
    event: str = "offload",
) -> list[TransferRecord]:
    """Scaffold the shoot folder and transfer files, ledgering each success."""
    pairs = plan_destinations(files, shoot_dir)
    problems = preflight_collisions(pairs)
    if problems:
        raise CollisionError("Destination collisions:\n  " + "\n  ".join(problems))
    scaffold_shoot(shoot_dir, has_video)
    records: list[TransferRecord] = []
    for item, destination in pairs:
        status, digest = operation(item.source, destination)
        record = TransferRecord(item, destination, digest, status)
        ledger.append([ledger_entry(record, event, source_label)])
        records.append(record)
    return records
