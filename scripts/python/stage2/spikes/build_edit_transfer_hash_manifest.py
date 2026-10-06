"""Hash-manifest originals before and after an edit-transfer step (ADR 0004).

Records path, size, mtime, and SHA-256 for files in one folder that match a
glob, or compares two such manifests. Manifests name client folders, so the
script refuses to write them inside the git checkout.

    build_edit_transfer_hash_manifest.py build --root <folder> --glob 'JB0001[0-5].*' --output <private>/pre.json
    build_edit_transfer_hash_manifest.py compare <private>/pre.json <private>/post.json
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.python.common import read_json, write_json

REPO_ROOT = Path(__file__).resolve().parents[4]
CHUNK_SIZE = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refuse_inside_repo(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise SystemExit(f"Refusing to write a private manifest inside the git checkout: {path}")


def build_manifest(root: Path, pattern: str) -> dict:
    files = sorted(p for p in root.glob(pattern) if p.is_file())
    return {
        "artifact": "edit_transfer_hash_manifest",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "glob": pattern,
        "file_count": len(files),
        "files": {
            p.name: {
                "size_bytes": p.stat().st_size,
                "mtime_epoch": p.stat().st_mtime,
                "sha256": sha256_file(p),
            }
            for p in files
        },
    }


def compare_manifests(pre: dict, post: dict) -> dict:
    """Content changes are SHA-256 or size differences; mtime-only changes are listed apart."""
    pre_files, post_files = pre["files"], post["files"]
    changed = sorted(
        name
        for name in pre_files.keys() & post_files.keys()
        if pre_files[name]["sha256"] != post_files[name]["sha256"]
        or pre_files[name]["size_bytes"] != post_files[name]["size_bytes"]
    )
    touched = sorted(
        name
        for name in pre_files.keys() & post_files.keys()
        if name not in changed and pre_files[name]["mtime_epoch"] != post_files[name]["mtime_epoch"]
    )
    missing = sorted(pre_files.keys() - post_files.keys())
    added = sorted(post_files.keys() - pre_files.keys())
    return {
        "identical": not (changed or missing or added),
        "content_changed": changed,
        "mtime_only_changed": touched,
        "missing": missing,
        "added": added,
        "compared_count": len(pre_files.keys() & post_files.keys()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Hash files matching a glob in one folder.")
    build.add_argument("--root", type=Path, required=True)
    build.add_argument("--glob", required=True)
    build.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare", help="Compare a pre and a post manifest.")
    compare.add_argument("pre", type=Path)
    compare.add_argument("post", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "build":
        refuse_inside_repo(args.output)
        manifest = build_manifest(args.root, args.glob)
        write_json(args.output, manifest)
        print(f"{manifest['file_count']} file(s) hashed -> {args.output}")
        return 0

    result = compare_manifests(read_json(args.pre), read_json(args.post))
    for key in ("content_changed", "mtime_only_changed", "missing", "added"):
        if result[key]:
            print(f"{key}: {', '.join(result[key])}")
    print(f"{'IDENTICAL' if result['identical'] else 'CHANGED'} ({result['compared_count']} file(s) compared)")
    return 0 if result["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
