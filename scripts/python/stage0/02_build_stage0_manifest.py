"""Stage 0 step 02: build a compact manifest from per-run offload manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.python.common import ensure_parent_dir, read_json


DEFAULT_OFFLOAD_DIR = "outputs/stage0/offloads"
DEFAULT_OUTPUT = "outputs/stage0/stage0_manifest.json"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for Stage 0 manifest generation."""
    parser = argparse.ArgumentParser(
        description="Build a compact Stage 0 manifest from offload run manifests."
    )
    parser.add_argument("--offload-dir", default=DEFAULT_OFFLOAD_DIR)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    """Calculate a SHA-256 digest for one local artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path) -> dict[str, object]:
    """Return a compact reference for a local artifact path."""
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def write_ordered_json(path: str | Path, payload: dict[str, object]) -> Path:
    """Write JSON while preserving semantic key order."""
    target = ensure_parent_dir(path)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target


def offload_runs(offload_dir: Path) -> list[dict[str, object]]:
    """Return one entry per run manifest, oldest first."""
    runs: list[dict[str, object]] = []
    for order, path in enumerate(sorted(offload_dir.glob("*.json")), start=1):
        payload = read_json(path)
        summary = payload.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        runs.append(
            {
                "order": order,
                "role": "offload_run_manifest",
                "status": payload.get("status"),
                "pipeline_step": payload.get("pipeline_step"),
                "produced_by": "scripts/python/stage0/01_run_sd_offload.py",
                "summary": summary,
                "artifact": artifact_ref(path),
            }
        )
    return runs


def build_manifest(args: argparse.Namespace) -> dict[str, object]:
    """Build the stable Stage 0 manifest payload."""
    offload_dir = Path(args.offload_dir)
    if not offload_dir.is_dir():
        raise SystemExit(f"Offload manifest folder not found: {offload_dir}")
    runs = offload_runs(offload_dir)

    def total(key: str) -> int:
        return sum(
            int(value)
            for run in runs
            if isinstance(run["summary"], dict)
            and isinstance(value := run["summary"].get(key), int)
        )

    return {
        "stage": "stage0_sd_ingest_offload",
        "status": "complete" if all(run["status"] == "complete" for run in runs) else "attention",
        "summary": {
            "offload_run_count": len(runs),
            "failed_run_count": sum(1 for run in runs if run["status"] != "complete"),
            "shoot_count": total("shoot_count"),
            "file_count": total("file_count"),
            "transferred_count": total("transferred_count"),
            "inbox_shoot_count": total("inbox_shoot_count"),
            "total_bytes": total("total_bytes"),
        },
        "pipeline_step": "02_build_stage0_manifest",
        "purpose": (
            "Compact index of Stage 0 card offloads. Each run manifest records "
            "per-file SHA-256 hashes, destinations, classifier suggestions, and "
            "operator answers; this manifest hashes those run manifests."
        ),
        "downstream_stage": "stage1_metadata_foundation (Lightroom import from the SSD)",
        "offload_runs": runs,
    }


def main() -> None:
    """Write the Stage 0 manifest."""
    args = parse_args()
    manifest = build_manifest(args)
    target = write_ordered_json(args.output, manifest)
    summary = manifest["summary"]
    assert isinstance(summary, dict)
    print(f"Wrote {target} ({summary['offload_run_count']} offload runs)")


if __name__ == "__main__":
    main()
