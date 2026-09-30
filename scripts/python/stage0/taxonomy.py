"""Read the SSD folder taxonomy and build shoot-folder names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath

from scripts.python.stage0.inventory import MEDIA_EXTENSIONS
from scripts.python.stage0.volumes import access_denied


EN_DASH_SEPARATOR = " – "
SHOOT_FOLDER_MARKERS = frozenset({"photo", "video", "raw", "exports"})


@dataclass(frozen=True)
class FolderListing:
    """Children of one taxonomy folder, split by role."""

    subfolders: tuple[str, ...]
    shoot_folders: tuple[str, ...]


def is_ignored(name: str, extra: frozenset[str] = frozenset()) -> bool:
    """Return True for Lightroom catalog artifacts, dotfiles, and extra names."""
    return (
        name.startswith(".")
        or name.startswith("__LrC")
        or name.lower().endswith(".lrdata")
        or name in extra
    )


def is_shoot_folder(path: Path) -> bool:
    """Return True when a folder already holds a shoot (media or Photo/Video/RAW)."""
    try:
        for child in path.iterdir():
            if child.is_dir() and child.name.lower() in SHOOT_FOLDER_MARKERS:
                return True
            if child.is_file() and child.suffix.lower() in MEDIA_EXTENSIONS:
                return True
    except PermissionError as exc:
        raise access_denied(path) from exc
    return False


class TaxonomyReader:
    """Read-only view of the live SSD folder tree used to build dialog choices."""

    def __init__(self, root: Path, ignored_names: frozenset[str] = frozenset()) -> None:
        self.root = root
        self.ignored_names = ignored_names

    def listing(self, relpath: PurePosixPath) -> FolderListing:
        folder = self.root / relpath
        if not folder.is_dir():
            return FolderListing((), ())
        try:
            children = sorted(
                child
                for child in folder.iterdir()
                if child.is_dir() and not is_ignored(child.name, self.ignored_names)
            )
        except PermissionError as exc:
            raise access_denied(folder) from exc
        subfolders: list[str] = []
        shoots: list[str] = []
        for child in children:
            (shoots if is_shoot_folder(child) else subfolders).append(child.name)
        return FolderListing(tuple(subfolders), tuple(shoots))

    def exists(self, relpath: PurePosixPath) -> bool:
        return (self.root / relpath).exists()


class EmptyTaxonomy:
    """Stand-in used when the SSD is absent during a dry run."""

    def listing(self, relpath: PurePosixPath) -> FolderListing:
        return FolderListing((), ())

    def exists(self, relpath: PurePosixPath) -> bool:
        return False


def build_tree(
    reader: TaxonomyReader,
    relpath: PurePosixPath = PurePosixPath(),
    max_depth: int = 8,
) -> dict[str, object]:
    """Return a nested {name: subtree} dict; shoot folders map to None."""
    listing = reader.listing(relpath)
    tree: dict[str, object] = {}
    for name in listing.subfolders:
        tree[name] = build_tree(reader, relpath / name, max_depth - 1) if max_depth > 1 else {}
    for name in listing.shoot_folders:
        tree[name] = None
    return tree


def sanitize_component(text: str) -> str:
    """Make one folder-name component safe for macOS paths.

    Path separators and colons become hyphens, whitespace is collapsed,
    and leading dots or trailing dots/spaces are removed.
    """
    cleaned = re.sub(r"[/:\\]", "-", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned).strip()
    cleaned = cleaned.lstrip(".").rstrip(". ").strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"Folder name is empty after cleaning: {text!r}")
    return cleaned


def shoot_folder_name(subject: str, descriptor: str = "", location: str = "") -> str:
    """Return `Subject – Descriptor – Location`, skipping empty parts (en dash)."""
    parts = [sanitize_component(subject)]
    for optional in (descriptor, location):
        if optional and optional.strip():
            parts.append(sanitize_component(optional))
    return EN_DASH_SEPARATOR.join(parts)


def session_folder_name(session: str, year: int) -> str:
    """Return `<Session> <Year>` without duplicating a trailing year."""
    cleaned = sanitize_component(session)
    if re.search(rf"\b{year}$", cleaned):
        return cleaned
    return f"{cleaned} {year}"


def repeat_client_relpath(client: str, session: str, year: int) -> PurePosixPath:
    """Return `<Client>/<Session> <Year>` for repeat clients."""
    return PurePosixPath(sanitize_component(client)) / session_folder_name(session, year)


def inbox_relpath(inbox_folder: str, capture_date: date) -> PurePosixPath:
    """Return the fallback `_Inbox/<YYYY-MM-DD> – Unsorted` folder."""
    return PurePosixPath(inbox_folder) / f"{capture_date.isoformat()}{EN_DASH_SEPARATOR}Unsorted"


def parse_relpath(text: str) -> PurePosixPath:
    """Parse an operator-edited relative destination, cleaning each component."""
    components = [part for part in text.strip().strip("/").split("/") if part.strip()]
    if not components:
        raise ValueError("Destination path is empty.")
    return PurePosixPath(*(sanitize_component(part) for part in components))
