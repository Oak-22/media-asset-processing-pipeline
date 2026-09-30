"""Locate the camera card and the destination SSD for Stage 0 offloads."""

from __future__ import annotations

import plistlib
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


VOLUMES_ROOT = Path("/Volumes")
SONY_DCIM_FOLDER = re.compile(r"^\d{3}MSDCF$", re.IGNORECASE)
SONY_VIDEO_ROOT = Path("PRIVATE/M4ROOT")

DiskInfo = Callable[[Path], dict[str, object]]


class AccessDeniedError(RuntimeError):
    """Raised when macOS privacy controls block access to a volume."""


def access_denied(path: Path) -> AccessDeniedError:
    """Build an actionable error for a TCC-blocked path."""
    return AccessDeniedError(
        f"macOS blocked access to {path} (Operation not permitted). Grant "
        f"Full Disk Access, or Removable Volumes access, to {sys.executable} "
        "(and to the terminal app when running by hand) in System Settings > "
        "Privacy & Security, then retry."
    )


@dataclass(frozen=True)
class VolumeIdentity:
    """Identity fields for one mounted volume."""

    mount_point: Path
    volume_name: str
    volume_uuid: str | None
    device_identifier: str | None
    file_system: str | None

    @property
    def label(self) -> str:
        """Return a filename-safe label for manifests."""
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", self.volume_name).strip("-")
        return cleaned or "card"

    def to_record(self) -> dict[str, object]:
        """Return a JSON-ready record."""
        return {
            "mount_point": str(self.mount_point),
            "volume_name": self.volume_name,
            "volume_uuid": self.volume_uuid,
            "device_identifier": self.device_identifier,
            "file_system": self.file_system,
        }


def diskutil_info(path: Path) -> dict[str, object]:
    """Return `diskutil info -plist` output for a mount, or {} when unavailable."""
    try:
        completed = subprocess.run(
            ["diskutil", "info", "-plist", str(path)],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {}
    try:
        payload = plistlib.loads(completed.stdout)
    except plistlib.InvalidFileException:
        return {}
    return payload if isinstance(payload, dict) else {}


def volume_identity(path: Path, info_fn: DiskInfo = diskutil_info) -> VolumeIdentity:
    """Describe the volume mounted at `path`."""
    info = info_fn(path)

    def text(key: str) -> str | None:
        value = info.get(key)
        return str(value) if value else None

    return VolumeIdentity(
        mount_point=path,
        volume_name=text("VolumeName") or path.name,
        volume_uuid=text("VolumeUUID"),
        device_identifier=text("DeviceIdentifier"),
        file_system=text("FilesystemName") or text("FilesystemType"),
    )


def is_camera_card(path: Path) -> bool:
    """Return True when `path` has a DCIM/ folder with a Sony card layout."""
    dcim = path / "DCIM"
    if not dcim.is_dir():
        return False
    try:
        has_sony_dcim = any(
            child.is_dir() and SONY_DCIM_FOLDER.match(child.name)
            for child in dcim.iterdir()
        )
    except PermissionError as exc:
        raise access_denied(dcim) from exc
    return has_sony_dcim or (path / SONY_VIDEO_ROOT).is_dir()


def mounted_volumes(volumes_root: Path = VOLUMES_ROOT) -> list[Path]:
    """Return mounted volume paths under /Volumes."""
    if not volumes_root.is_dir():
        return []
    return sorted(
        child
        for child in volumes_root.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    )


def find_volume_by_uuid(
    volume_uuid: str,
    volumes_root: Path = VOLUMES_ROOT,
    info_fn: DiskInfo = diskutil_info,
) -> VolumeIdentity | None:
    """Return the mounted volume whose VolumeUUID matches, if any."""
    wanted = volume_uuid.upper()
    for mount in mounted_volumes(volumes_root):
        identity = volume_identity(mount, info_fn)
        if identity.volume_uuid and identity.volume_uuid.upper() == wanted:
            return identity
    return None


def find_cards(
    volumes_root: Path = VOLUMES_ROOT,
    exclude: set[Path] | None = None,
) -> list[Path]:
    """Return mounted volumes that look like Sony camera cards."""
    excluded = {path.resolve() for path in exclude or set()}
    cards: list[Path] = []
    for mount in mounted_volumes(volumes_root):
        if mount.resolve() in excluded:
            continue
        if is_camera_card(mount):
            cards.append(mount)
    return cards
