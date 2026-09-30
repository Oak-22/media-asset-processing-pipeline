"""Shared builders for Stage 0 tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath

from scripts.python.stage0.inventory import CardFile, media_kind


def card_file(
    name: str,
    capture_time: datetime,
    *,
    root: Path = Path("/card"),
    folder: str = "DCIM/100MSDCF",
    size_bytes: int = 100,
    gps: tuple[float, float] | None = None,
) -> CardFile:
    """Build a CardFile without touching the filesystem."""
    relative = PurePosixPath(folder) / name
    kind = media_kind(relative)
    assert kind is not None, name
    return CardFile(
        source=root / relative,
        relative_path=relative,
        media=kind[0],
        role=kind[1],
        size_bytes=size_bytes,
        capture_time=capture_time,
        capture_time_source="exif_datetime_original",
        gps=gps,
    )
