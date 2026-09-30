"""Compare Crop > Auto straighten angles with Upright Level predictions.

Spike: can Transform > Upright Level stand in for the Crop tool's Auto
button, which the Lightroom SDK cannot invoke? Both inputs are written by
lightroom_plugins/crop-auto-vs-upright-level-spike.lrplugin from two Virtual
Copy branches of the same originals, so records are matched on asset_key.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.python.common import ensure_parent_dir, read_json


DEFAULT_LEVEL_PROBE = "outputs/lightroom_sdk/lightroom_sdk_upright_level_probe.json"
DEFAULT_CROP_AUTO_RECORD = "outputs/lightroom_sdk/lightroom_sdk_crop_auto_angle_record.json"
DEFAULT_OUTPUT = (
    "outputs/lightroom_sdk/lightroom_sdk_crop_auto_vs_upright_level_comparison.json"
)
AGREEMENT_THRESHOLDS_DEGREES = (0.1, 0.25, 0.5, 1.0)
# Angles smaller than this are treated as "already level" for direction checks.
DIRECTION_MIN_DEGREES = 0.05


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the Crop Auto vs Upright Level comparison."""
    parser = argparse.ArgumentParser(
        description="Compare Crop > Auto angles with Upright Level predictions."
    )
    parser.add_argument("--level-probe", default=DEFAULT_LEVEL_PROBE)
    parser.add_argument("--crop-auto-record", default=DEFAULT_CROP_AUTO_RECORD)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def compare_records(
    level_records: list[dict], crop_auto_records: list[dict]
) -> tuple[list[dict], list[str]]:
    """Pair records by asset_key; return comparisons and assets without a Level rotation."""
    level_by_asset = {record["asset_key"]: record for record in level_records}
    comparisons, missing_level = [], []

    for crop_auto in crop_auto_records:
        asset_key = crop_auto["asset_key"]
        predicted = level_by_asset.get(asset_key, {}).get("predicted_crop_angle_degrees")
        if predicted is None:
            missing_level.append(asset_key)
            continue
        actual = crop_auto["crop_angle_degrees"]
        comparisons.append(
            {
                "asset_key": asset_key,
                "crop_auto_angle_degrees": actual,
                "upright_level_predicted_angle_degrees": predicted,
                "difference_degrees": round(predicted - actual, 4),
                "absolute_difference_degrees": round(abs(predicted - actual), 4),
            }
        )

    comparisons.sort(key=lambda record: -record["absolute_difference_degrees"])
    return comparisons, missing_level


def summarize(comparisons: list[dict], missing_level: list[str]) -> dict:
    """Agreement statistics for the paired records."""
    differences = [record["absolute_difference_degrees"] for record in comparisons]
    tilted = [
        record
        for record in comparisons
        if abs(record["crop_auto_angle_degrees"]) > DIRECTION_MIN_DEGREES
    ]
    same_direction = sum(
        (record["crop_auto_angle_degrees"] > 0)
        == (record["upright_level_predicted_angle_degrees"] > 0)
        for record in tilted
    )
    return {
        "compared_count": len(comparisons),
        "missing_level_rotation_count": len(missing_level),
        "median_absolute_difference_degrees": (
            round(statistics.median(differences), 4) if differences else None
        ),
        "max_absolute_difference_degrees": max(differences, default=None),
        "within_threshold_counts": {
            f"{threshold}_degrees": sum(value <= threshold for value in differences)
            for threshold in AGREEMENT_THRESHOLDS_DEGREES
        },
        "same_direction_count": same_direction,
        "same_direction_eligible_count": len(tilted),
    }


def write_ordered_json(path: str | Path, payload: dict) -> Path:
    """Write JSON preserving semantic key order for human review."""
    target = ensure_parent_dir(path)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    args = parse_args()
    level_probe = read_json(args.level_probe)
    crop_auto_record = read_json(args.crop_auto_record)

    comparisons, missing_level = compare_records(
        level_probe["records"], crop_auto_record["records"]
    )
    summary = summarize(comparisons, missing_level)

    write_ordered_json(
        args.output,
        {
            "spike": "crop_auto_vs_upright_level",
            "artifact": "crop_auto_vs_upright_level_comparison",
            "status": "complete",
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": summary,
            "inputs": {
                "upright_level_probe": args.level_probe,
                "crop_auto_angle_record": args.crop_auto_record,
                "match_key": "asset_key",
            },
            "records": comparisons,
            "missing_level_rotation_asset_keys": missing_level,
        },
    )

    within = summary["within_threshold_counts"]
    print(
        f"{summary['compared_count']} compared | "
        f"median |diff| {summary['median_absolute_difference_degrees']} deg | "
        f"max {summary['max_absolute_difference_degrees']} deg | "
        + " | ".join(f"<= {key}: {value}" for key, value in within.items())
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
