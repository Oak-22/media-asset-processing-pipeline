"""Score the JPEG-to-RAW edit-transfer pilot (P1-P5, P7) from its renders.

Input is the private pilot root written by
lightroom_plugins/jpeg-to-raw-edit-transfer-spike.lrplugin (RunPilot.lua):
`pilot_manifest.json` plus 16-bit TIFF renders. The camera JPEG baseline
is decoded with `sips` into the pilot root. The report names photos and
folders, so it is written outside the git checkout (default: the Desktop).

Gates follow PLAN-jpeg-to-raw-edit-transfer.md, step 5:

- P1 determinism: max ΔE00 between repeat exports <= 0.05
- P2 identity: mean ΔE00 <= 0.3, keys that do not round-trip listed
- P3 base profile: lowest median ΔE00 vs the camera JPEG on >= 5 of 6 pairs, and <= 3
- P4 WB scale: R² >= 0.95, conversion slopes agree within ±20%
- P5 tone method: lower median ΔE00 wins; must reach |ΔL* p50| <= 2
- P7 SDK mechanics: profile encoding, Auto Tone, partial apply, restore
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.python.common import read_json, write_json
from scripts.python.stage2.spikes import edit_transfer_metrics as m

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PUBLIC_SUMMARY = "outputs/lightroom_sdk/lightroom_sdk_jpeg_to_raw_edit_transfer_pilot_summary.json"
DEFAULT_REPORT_DIR = Path.home() / "Desktop" / "edit-transfer-pilot-report"
PROFILE_VARIANTS = ("raw_camera_standard", "raw_adobe_color", "raw_camera_neutral")
TONE_VARIANTS = ("tone_auto", "tone_offset", "tone_verbatim")
SAME_RENDER_DE = 0.1
DISTINCT_RENDER_DE = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score the JPEG-to-RAW edit-transfer pilot.")
    parser.add_argument("--pilot-root", type=Path, required=True, help="<event>/Photo/RAW Edit Transfer/pilot")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--public-summary",
        type=Path,
        help="Also write a de-identified aggregate summary (no names, paths, or per-photo rows), e.g. "
        + DEFAULT_PUBLIC_SUMMARY,
    )
    return parser.parse_args()


def refuse_inside_repo(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise SystemExit(f"Refusing to write private pilot output inside the git checkout: {path}")


def rounded(value, places: int = 3):
    if isinstance(value, float):
        return None if np.isnan(value) else round(value, places)
    if isinstance(value, dict):
        return {k: rounded(v, places) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v, places) for v in value]
    return value


class Pair:
    """Renders and Lab images for one JPEG + ARW pair, loaded on demand."""

    def __init__(self, record: dict, render_dir: Path, baseline_dir: Path, long_edge: int):
        self.record = record
        self.key = record["asset_key"]
        self.render_dir = render_dir
        self.baseline_dir = baseline_dir
        self.long_edge = long_edge
        self.entries = {e["variant"]: e for e in record["renders"] if e.get("file") and not e.get("error")}
        self._rgb: dict[str, np.ndarray] = {}

    def has(self, variant: str) -> bool:
        return variant in self.entries

    def rgb(self, variant: str) -> np.ndarray:
        if variant not in self._rgb:
            if variant == "camera_jpeg":
                self._rgb[variant] = self._upright_camera_jpeg()
            else:
                self._rgb[variant] = m.load_tiff_srgb01(self.render_dir / self.entries[variant]["file"])
        return self._rgb[variant]

    def lab(self, variant: str) -> np.ndarray:
        return m.srgb_to_lab(self.rgb(variant))

    def _upright_camera_jpeg(self) -> np.ndarray:
        """sips keeps the stored pixel order; rotate portrait frames to match Lightroom's render."""
        image = m.load_tiff_srgb01(self.camera_jpeg_path())
        reference = self.rgb("jpg_zero") if self.has("jpg_zero") else None
        if reference is None or (image.shape[0] > image.shape[1]) == (reference.shape[0] > reference.shape[1]):
            return image
        candidates = [np.rot90(image, k) for k in (1, 3)]
        errors = [np.abs(m.match_shape(c, reference.shape[:2]) - reference).mean() for c in candidates]
        return candidates[int(np.argmin(errors))]

    def camera_jpeg_path(self) -> Path:
        output = self.baseline_dir / f"{self.key}__camera_jpeg.tif"
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "sips", "-s", "format", "tiff",
                    "--resampleHeightWidthMax", str(self.long_edge),
                    self.record["jpeg_master_path"], "--out", str(output),
                ],
                check=True,
                capture_output=True,
            )
        return output


def compare_frames(reference_rgb: np.ndarray, moving_rgb: np.ndarray, clipped: np.ndarray | None, align: bool) -> dict:
    """Align (optional) moving onto reference, then score over the trimmed overlap."""
    moving_rgb = m.match_shape(moving_rgb, reference_rgb.shape[:2])
    ref_lab, mov_lab = m.srgb_to_lab(reference_rgb), m.srgb_to_lab(moving_rgb)
    alignment = m.Similarity()
    if align:
        alignment = m.estimate_similarity(ref_lab[..., 0], mov_lab[..., 0])
        mov_lab = m.apply_alignment(mov_lab, alignment)
    valid = m.border_mask(ref_lab.shape[:2]) & ~np.isnan(mov_lab).any(axis=-1)
    mov_lab = np.nan_to_num(mov_lab)
    if clipped is not None:
        clipped = m.match_shape(clipped, ref_lab.shape[:2])
    result = m.compare_lab(ref_lab, mov_lab, valid, clipped)
    result["alignment"] = {
        "scale": alignment.scale,
        "rotation_degrees": alignment.rotation_degrees,
        "shift_x_px": alignment.shift_x,
        "shift_y_px": alignment.shift_y,
    }
    result["gradient_correlation"] = m.gradient_correlation(ref_lab[..., 0], mov_lab[..., 0], valid)
    return result


def p1_determinism(pairs: list[Pair]) -> dict:
    rows = {}
    for pair in pairs:
        if pair.has("raw_camera_standard") and pair.has("raw_camera_standard_repeat"):
            a, b = pair.lab("raw_camera_standard"), pair.lab("raw_camera_standard_repeat")
            de = m.delta_e_2000(a, m.match_shape(b, a.shape[:2]))
            rows[pair.key] = {"de_max": float(de.max()), "de_mean": float(de.mean())}
    worst = max((r["de_max"] for r in rows.values()), default=float("nan"))
    return {"pass": bool(rows) and worst <= 0.05, "rule": "max ΔE00 <= 0.05", "worst_de_max": worst, "per_pair": rows}


def p2_identity(identity: dict | None, render_dir: Path) -> dict:
    if not identity or identity.get("error"):
        return {"pass": False, "error": (identity or {}).get("error", "no identity record")}
    files = {e["variant"]: e.get("file") for e in identity["renders"]}
    errors = [e["error"] for e in identity["renders"] if e.get("error")]
    if errors or not files.get("id_source") or not files.get("id_copy"):
        return {"pass": False, "error": "; ".join(errors) or "identity renders missing"}
    a = m.srgb_to_lab(m.load_tiff_srgb01(render_dir / files["id_source"]))
    b = m.srgb_to_lab(m.match_shape(m.load_tiff_srgb01(render_dir / files["id_copy"]), a.shape[:2]))
    de = m.delta_e_2000(a, b)
    return {
        "pass": float(de.mean()) <= 0.3,
        "rule": "mean ΔE00 <= 0.3",
        "de_mean": float(de.mean()),
        "de_p99": float(np.percentile(de, 99)),
        "de_max": float(de.max()),
        "keys_not_round_tripping": identity.get("missing_or_different_keys", []),
    }


def p3_profiles(pairs: list[Pair]) -> dict:
    per_pair, sanity = {}, {}
    for pair in pairs:
        camera = pair.rgb("camera_jpeg")
        clipped = m.clip_mask(camera)
        per_pair[pair.key] = {
            variant: compare_frames(camera, pair.rgb(variant), clipped, align=True)
            for variant in PROFILE_VARIANTS
            if pair.has(variant)
        }
        if pair.has("jpg_zero"):
            sanity[pair.key] = compare_frames(camera, pair.rgb("jpg_zero"), clipped, align=True)
    wins = sum(
        1
        for rows in per_pair.values()
        if "raw_camera_standard" in rows
        and min(rows, key=lambda v: rows[v]["de_median"]) == "raw_camera_standard"
    )
    cs_medians = [rows["raw_camera_standard"]["de_median"] for rows in per_pair.values() if "raw_camera_standard" in rows]
    cs_overall = statistics.median(cs_medians) if cs_medians else float("nan")
    needed = max(len(per_pair) - 1, 1)
    return {
        "pass": wins >= needed and cs_overall <= 3,
        "rule": f"Camera Standard has the lowest median ΔE00 on >= {needed} of {len(per_pair)} pairs, and <= 3",
        "camera_standard_wins": wins,
        "camera_standard_median_of_medians": cs_overall,
        "per_pair": per_pair,
        "sanity_jpeg_zero_vs_camera_jpeg": sanity,
    }


def p4_white_balance(pairs: list[Pair], settings: dict) -> dict:
    per_pair, conversions = {}, []
    mired = np.array(settings["wb_mired_steps"], dtype=float)
    tint = np.array(settings["wb_tint_steps"], dtype=float)
    inc = np.array(settings["jpeg_increment_steps"], dtype=float)
    grids = {
        "raw_temp": [f"raw_wb_mired{int(s):+d}" for s in mired],
        "raw_tint": [f"raw_wb_tint{int(s):+d}" for s in tint],
        "jpeg_temp": [f"jpg_wb_temp{int(s):+d}" for s in inc],
        "jpeg_tint": [f"jpg_wb_tint{int(s):+d}" for s in inc],
    }
    for pair in pairs:
        required = ["raw_camera_standard", "jpg_zero"] + [v for names in grids.values() for v in names]
        if not all(pair.has(v) for v in required):
            continue
        raw_center = pair.lab("raw_camera_standard")
        jpeg_center = pair.lab("jpg_zero")
        raw_valid = m.border_mask(raw_center.shape[:2]) & ~m.clip_mask(pair.rgb("raw_camera_standard"))
        jpeg_valid = m.border_mask(jpeg_center.shape[:2]) & ~m.clip_mask(pair.rgb("jpg_zero"))

        def shifts(center, valid, names):
            return np.array([m.wb_shift(center, m.match_shape(pair.lab(n), center.shape[:2]), valid) for n in names])

        raw_t, r2_raw_t = m.wb_response(mired, shifts(raw_center, raw_valid, grids["raw_temp"]))
        raw_g, r2_raw_g = m.wb_response(tint, shifts(raw_center, raw_valid, grids["raw_tint"]))
        jpg_t, r2_jpg_t = m.wb_response(inc, shifts(jpeg_center, jpeg_valid, grids["jpeg_temp"]))
        jpg_g, r2_jpg_g = m.wb_response(inc, shifts(jpeg_center, jpeg_valid, grids["jpeg_tint"]))
        conversion = m.wb_conversion(raw_t, raw_g, jpg_t, jpg_g)
        conversions.append(conversion)
        per_pair[pair.key] = {
            "lab_per_mired": raw_t.tolist(),
            "lab_per_raw_tint": raw_g.tolist(),
            "lab_per_jpeg_temp_increment": jpg_t.tolist(),
            "lab_per_jpeg_tint_increment": jpg_g.tolist(),
            "r2": {"raw_temp": r2_raw_t, "raw_tint": r2_raw_g, "jpeg_temp": r2_jpg_t, "jpeg_tint": r2_jpg_g},
            "mired_per_jpeg_temp_increment": float(conversion[0, 0]),
            "raw_tint_per_jpeg_tint_increment": float(conversion[1, 1]),
            "conversion_matrix": conversion.tolist(),
        }
    if not conversions:
        return {"pass": False, "error": "no complete WB grids"}
    stack = np.array(conversions)
    median = np.median(stack, axis=0)
    min_r2 = min(min(v for v in row["r2"].values()) for row in per_pair.values())

    def agreement(index: tuple[int, int]) -> float:
        reference = median[index]
        return float(np.max(np.abs(stack[(slice(None),) + index] - reference)) / abs(reference)) if reference else float("inf")

    spread_temp, spread_tint = agreement((0, 0)), agreement((1, 1))
    return {
        "pass": min_r2 >= 0.95 and spread_temp <= 0.2 and spread_tint <= 0.2,
        "rule": "R² >= 0.95 on every fit; per-pair slopes within ±20% of the median",
        "median_mired_per_jpeg_temp_increment": float(median[0, 0]),
        "median_raw_tint_per_jpeg_tint_increment": float(median[1, 1]),
        "median_conversion_matrix": median.tolist(),
        "min_r2": min_r2,
        "max_relative_spread_temp": spread_temp,
        "max_relative_spread_tint": spread_tint,
        "group_photo_prediction": "not measurable: the group photo was edited as a RAW, so it has no JPEG WB increment to predict from",
        "per_pair": per_pair,
    }


def p5_tone(pairs: list[Pair]) -> dict:
    per_pair = {}
    for pair in pairs:
        if not pair.has("jpg_asis"):
            continue
        clipped = m.clip_mask(pair.rgb("camera_jpeg"))
        reference = pair.rgb("jpg_asis")
        clipped = m.match_shape(clipped, reference.shape[:2])
        per_pair[pair.key] = {
            variant: compare_frames(reference, pair.rgb(variant), clipped, align=True)
            for variant in TONE_VARIANTS
            if pair.has(variant)
        }
    summary = {}
    for variant in TONE_VARIANTS:
        medians = [rows[variant]["de_median"] for rows in per_pair.values() if variant in rows]
        dl = [abs(rows[variant]["dL_p50"]) for rows in per_pair.values() if variant in rows]
        if medians:
            summary[variant] = {
                "median_de_median": statistics.median(medians),
                "max_abs_dL_p50": max(dl),
                "pairs": len(medians),
            }
    if not summary:
        return {"pass": False, "error": "no tone renders"}
    winner = min(summary, key=lambda v: summary[v]["median_de_median"])
    return {
        "pass": summary[winner]["max_abs_dL_p50"] <= 2,
        "rule": "lower median ΔE00 wins; winner must reach |ΔL* p50| <= 2 on every pair",
        "winner": winner,
        "summary": summary,
        "per_pair": per_pair,
    }


def noise_match(pairs: list[Pair], settings: dict) -> dict:
    per_pair = {}
    for pair in pairs:
        if not pair.has("jpg_asis_noise_crop"):
            continue
        target = m.flat_region_noise(pair.lab("jpg_asis_noise_crop")[..., 0])
        amounts, sigmas = [], []
        for amount in settings["nr_values"]:
            variant = f"raw_nr{int(amount):02d}_noise_crop"
            if pair.has(variant):
                amounts.append(float(amount))
                sigmas.append(m.flat_region_noise(pair.lab(variant)[..., 0]))
        if amounts:
            per_pair[pair.key] = {
                "jpeg_sigma_L": target,
                "raw_sigma_L_by_nr": dict(zip([int(a) for a in amounts], sigmas)),
                "matched_nr": m.match_noise_level(amounts, sigmas, target),
            }
    matched = [row["matched_nr"] for row in per_pair.values()]
    recommended = int(5 * round(statistics.median(matched) / 5)) if matched else None
    return {
        "recommended_luminance_nr": recommended,
        "method": "flat-tile high-pass sigma of L* on a central 20% crop, RAW NR sweep vs the edited JPEG",
        "per_pair": per_pair,
    }


def p7_mechanics(pairs: list[Pair], manifest: dict, profile_reference: dict | None) -> dict:
    readbacks, unexpected, export_changes, auto_tone, restores, comparisons = {}, {}, {}, {}, {}, {}
    for pair in pairs:
        cs = pair.entries.get("raw_camera_standard", {}).get("readback") or {}
        readbacks[pair.key] = {k: cs.get(k) for k in ("CameraProfile", "CameraProfileDigest", "Look")}
        for entry in pair.record["renders"]:
            if entry.get("unexpected_changed_keys"):
                unexpected[f"{pair.key}/{entry['variant']}"] = entry["unexpected_changed_keys"]
            if entry.get("changed_during_export_keys"):
                export_changes[f"{pair.key}/{entry['variant']}"] = entry["changed_during_export_keys"]
        auto = pair.entries.get("tone_auto")
        auto_tone[pair.key] = {
            "resolved": bool(auto and auto["readback"].get("AutoTone") is not True and auto["readback"].get("Exposure2012") not in (None, -999999)),
            "wait_seconds": auto.get("auto_tone_wait_seconds") if auto else None,
            "values": {k: auto["readback"].get(k) for k in ("Exposure2012", "Contrast2012", "Highlights2012", "Shadows2012", "Whites2012", "Blacks2012", "Vibrance", "Saturation")} if auto else None,
        }
        restores[pair.key] = {"jpeg": pair.record.get("jpeg_restore"), "raw": pair.record.get("raw_restore")}

        def de(a: str, b: str):
            if not (pair.has(a) and pair.has(b)):
                return None
            x = pair.lab(a)
            return float(np.median(m.delta_e_2000(x, m.match_shape(pair.lab(b), x.shape[:2]))))

        comparisons[pair.key] = {
            "cs_vs_cs_digest_kept": de("raw_camera_standard", "p7_cs_digest_kept"),
            "cs_vs_adobe_standard_no_look": de("raw_camera_standard", "p7_adobe_standard_no_look"),
            "cs_vs_camera_neutral": de("raw_camera_standard", "raw_camera_neutral"),
            "cs_look_kept_vs_adobe_color": de("p7_cs_look_kept", "raw_adobe_color"),
            "cs_look_kept_vs_cs": de("p7_cs_look_kept", "raw_camera_standard"),
        }

    def all_true(values, test) -> bool:
        values = [v for v in values if v is not None]
        return bool(values) and all(test(v) for v in values)

    profile_resolves = all_true([c["cs_vs_adobe_standard_no_look"] for c in comparisons.values()], lambda v: v > DISTINCT_RENDER_DE)
    digest_irrelevant = all_true([c["cs_vs_cs_digest_kept"] for c in comparisons.values()], lambda v: v < SAME_RENDER_DE)
    leftover_look_overrides = all_true([c["cs_look_kept_vs_adobe_color"] for c in comparisons.values()], lambda v: v < SAME_RENDER_DE)
    look_cleared = all(not rb.get("Look") for rb in readbacks.values())
    restore_ok = all((r["jpeg"] or {}).get("ok") and (r["raw"] or {}).get("ok") for r in restores.values())
    auto_ok = all(v["resolved"] for v in auto_tone.values())

    reference = None
    if profile_reference:
        reference = [
            {k: r.get(k) for k in ("camera_profile", "camera_profile_digest", "look")} | {"asset_key": r["identity"].get("asset_key")}
            for r in profile_reference.get("records", [])
        ]
    return {
        "pass": profile_resolves and look_cleared and auto_ok and not unexpected and restore_ok,
        "rule": "profile renders distinctly with no leftover Look; Auto Tone resolves; partial apply changes only payload keys; restore reads back exactly",
        "camera_standard_resolves_to_a_distinct_render": profile_resolves,
        "digest_irrelevant_when_name_set": digest_irrelevant,
        "leftover_adobe_color_look_overrides_profile": leftover_look_overrides,
        "look_cleared_on_readback": look_cleared,
        "camera_standard_readback": readbacks,
        "gui_profile_reference": reference,
        "render_comparisons_median_de": comparisons,
        "auto_tone": auto_tone,
        "auto_tone_resolved_everywhere": auto_ok,
        "unexpected_changed_keys": unexpected,
        "keys_changed_during_export": export_changes,
        "restore": restores,
        "restore_exact_everywhere": restore_ok,
        "thresholds": {"same_render_de": SAME_RENDER_DE, "distinct_render_de": DISTINCT_RENDER_DE},
    }


def master_file_check(manifest: dict) -> dict:
    before, after = manifest.get("master_files_before") or {}, manifest.get("master_files_after") or {}
    changed = sorted(
        f"{key}/{kind}"
        for key in before
        for kind in before[key]
        if before[key][kind] != (after.get(key) or {}).get(kind)
    )
    return {"unchanged": bool(before) and not changed, "changed": changed, "source": "plug-in size/mtime snapshot"}


def spread(values: list[float]) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {}
    return {"min": min(values), "median": statistics.median(values), "max": max(values), "n": len(values)}


def build_public_summary(report: dict) -> dict:
    """Aggregate-only view of the report: counts and metric spreads, no asset keys or paths."""
    gates = report["gates"]
    p3, p4, p5, p7 = (gates[k] for k in ("P3_base_profile", "P4_white_balance", "P5_tone_method", "P7_sdk_mechanics"))
    profiles = {
        variant: {
            metric: spread([rows[variant][metric] for rows in p3.get("per_pair", {}).values() if variant in rows])
            for metric in ("de_median", "de_median_exposure_matched", "dL_mean", "da_mean", "db_mean")
        }
        for variant in PROFILE_VARIANTS
    }
    tone = {
        variant: {
            metric: spread([rows[variant][metric] for rows in p5.get("per_pair", {}).values() if variant in rows])
            for metric in ("de_median", "de_median_exposure_matched", "dL_p50", "db_mean")
        }
        for variant in TONE_VARIANTS
    }
    return {
        "spike": "jpeg_to_raw_edit_transfer",
        "artifact": "pilot_summary",
        "generated_at_utc": report["generated_at_utc"],
        "lightroom_version": report["lightroom_version"],
        "pair_count": report["pair_count"],
        "render_error_count": len(report["render_errors"]),
        "master_files_unchanged": report["master_files"]["unchanged"],
        "gate_results": {name: bool(gate.get("pass")) for name, gate in gates.items()},
        "P1_worst_repeat_de_max": gates["P1_determinism"].get("worst_de_max"),
        "P2_identity_de_mean": gates["P2_identity"].get("de_mean"),
        "P2_keys_not_round_tripping": gates["P2_identity"].get("keys_not_round_tripping"),
        "P3_camera_standard_wins": p3.get("camera_standard_wins"),
        "P3_profiles_vs_camera_jpeg": profiles,
        "P3_floor_jpeg_zero_vs_camera_jpeg_de_median": spread(
            [row["de_median"] for row in p3.get("sanity_jpeg_zero_vs_camera_jpeg", {}).values()]
        ),
        "P4_mired_per_jpeg_temp_increment": p4.get("median_mired_per_jpeg_temp_increment"),
        "P4_raw_tint_per_jpeg_tint_increment": p4.get("median_raw_tint_per_jpeg_tint_increment"),
        "P4_min_r2": p4.get("min_r2"),
        "P5_winner": p5.get("winner"),
        "P5_tone_vs_edited_jpeg": tone,
        "P7": {
            key: p7.get(key)
            for key in (
                "camera_standard_resolves_to_a_distinct_render",
                "digest_irrelevant_when_name_set",
                "leftover_adobe_color_look_overrides_profile",
                "look_cleared_on_readback",
                "auto_tone_resolved_everywhere",
                "restore_exact_everywhere",
            )
        },
        "P7_unexpected_changed_keys": sorted({k for keys in p7.get("unexpected_changed_keys", {}).values() for k in keys}),
        "P7_restore_differing_keys": sorted(
            {
                k
                for sides in p7.get("restore", {}).values()
                for side in sides.values()
                for k in (side or {}).get("differing_keys") or []
            }
        ),
        "noise_recommended_luminance_nr": report["noise"]["recommended_luminance_nr"],
        "noise_matched_nr": spread([row["matched_nr"] for row in report["noise"]["per_pair"].values()]),
    }


def gate_line(name: str, result: dict) -> str:
    status = "PASS" if result.get("pass") else "FAIL"
    detail = result.get("error") or result.get("rule", "")
    return f"| {name} | {status} | {detail} |"


def write_markdown(path: Path, report: dict) -> None:
    gates = report["gates"]
    lines = [
        "# Edit Transfer Pilot Report",
        "",
        f"Generated {report['generated_at_utc']} from {report['pair_count']} pair(s). Manifest status: {report['manifest_status']}.",
        "",
        "| Gate | Result | Rule |",
        "|---|---|---|",
        gate_line("P1 determinism", gates["P1_determinism"]),
        gate_line("P2 identity", gates["P2_identity"]),
        gate_line("P3 base profile", gates["P3_base_profile"]),
        gate_line("P4 WB scale", gates["P4_white_balance"]),
        gate_line("P5 tone method", gates["P5_tone_method"]),
        gate_line("P7 SDK mechanics", gates["P7_sdk_mechanics"]),
        "",
        "## Key numbers",
        "",
    ]
    p3, p4, p5, p7 = gates["P3_base_profile"], gates["P4_white_balance"], gates["P5_tone_method"], gates["P7_sdk_mechanics"]
    lines.append(f"- P1 worst max ΔE00 between repeat exports: {rounded(gates['P1_determinism'].get('worst_de_max'), 4)}")
    if "de_mean" in gates["P2_identity"]:
        lines.append(f"- P2 identity mean ΔE00: {rounded(gates['P2_identity']['de_mean'], 4)}; keys not round-tripping: {gates['P2_identity']['keys_not_round_tripping']}")
    if "per_pair" in p3:
        lines.append(f"- P3 Camera Standard wins {p3['camera_standard_wins']} of {len(p3['per_pair'])}; median of medians {rounded(p3['camera_standard_median_of_medians'])}")
        lines += ["", "| Pair | Camera Standard | Adobe Color | Camera Neutral |", "|---|---|---|---|"]
        for key, rows in p3["per_pair"].items():
            cells = [str(rounded(rows[v]["de_median"], 2)) if v in rows else "-" for v in PROFILE_VARIANTS]
            lines.append(f"| {key} | " + " | ".join(cells) + " |")
        lines.append("")
    if "median_mired_per_jpeg_temp_increment" in p4:
        lines.append(
            f"- P4 one JPEG temperature increment ≈ {rounded(p4['median_mired_per_jpeg_temp_increment'])} mired; "
            f"one JPEG tint increment ≈ {rounded(p4['median_raw_tint_per_jpeg_tint_increment'])} RAW tint; "
            f"min R² {rounded(p4['min_r2'])}; spread {rounded(p4['max_relative_spread_temp'])} / {rounded(p4['max_relative_spread_tint'])}"
        )
    if "summary" in p5:
        lines.append(f"- P5 winner: {p5['winner']}")
        for variant, row in p5["summary"].items():
            lines.append(f"  - {variant}: median ΔE00 {rounded(row['median_de_median'], 2)}, max |ΔL* p50| {rounded(row['max_abs_dL_p50'], 2)}")
    lines.append(f"- Recommended luminance NR: {report['noise']['recommended_luminance_nr']}")
    lines.append(
        f"- P7 Camera Standard resolves: {p7['camera_standard_resolves_to_a_distinct_render']}; "
        f"digest irrelevant: {p7['digest_irrelevant_when_name_set']}; "
        f"leftover Adobe Color Look overrides: {p7['leftover_adobe_color_look_overrides_profile']}; "
        f"Look cleared: {p7['look_cleared_on_readback']}; Auto Tone resolved: {p7['auto_tone_resolved_everywhere']}; "
        f"restore exact: {p7['restore_exact_everywhere']}; unexpected keys: {len(p7['unexpected_changed_keys'])}"
    )
    lines.append(f"- Master files unchanged (plug-in snapshot): {report['master_files']['unchanged']} {report['master_files']['changed'] or ''}")
    lines += ["", "Full numbers are in `pilot_report.json` next to this file.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    pilot_root = args.pilot_root.expanduser()
    report_dir = args.report_dir.expanduser()
    refuse_inside_repo(pilot_root)
    refuse_inside_repo(report_dir)

    manifest = read_json(pilot_root / "pilot_manifest.json")
    reference_path = pilot_root / "profile_reference.json"
    profile_reference = read_json(reference_path) if reference_path.exists() else None
    settings = manifest["settings"]
    render_dir = pilot_root / "renders"
    pairs = [
        Pair(record, render_dir, pilot_root / "baseline", settings["render_long_edge"])
        for record in manifest["pairs"]
        if not record.get("error")
    ]
    failed_pairs = {r["asset_key"]: r["error"] for r in manifest["pairs"] if r.get("error")}
    render_errors = {
        f"{r['asset_key']}/{e['variant']}": e["error"] for r in manifest["pairs"] for e in r["renders"] if e.get("error")
    }

    report = {
        "artifact": "edit_transfer_pilot_report",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest_status": manifest.get("status"),
        "lightroom_version": manifest.get("lightroom_version"),
        "pair_count": len(pairs),
        "failed_pairs": failed_pairs,
        "render_errors": render_errors,
        "gates": {
            "P1_determinism": p1_determinism(pairs),
            "P2_identity": p2_identity(manifest.get("identity"), render_dir),
            "P3_base_profile": p3_profiles(pairs),
            "P4_white_balance": p4_white_balance(pairs, settings),
            "P5_tone_method": p5_tone(pairs),
            "P7_sdk_mechanics": p7_mechanics(pairs, manifest, profile_reference),
        },
        "noise": noise_match(pairs, settings),
        "master_files": master_file_check(manifest),
        "raw_as_shot": {p.key: p.record.get("raw_as_shot") for p in pairs},
    }
    report = rounded(report, 4)
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / "pilot_report.json", report)
    write_markdown(report_dir / "pilot_report.md", report)
    if args.public_summary:
        write_json(args.public_summary, rounded(build_public_summary(report), 4))
        print(f"Public summary: {args.public_summary}")
    for name, gate in report["gates"].items():
        print(f"{name}: {'PASS' if gate.get('pass') else 'FAIL'}")
    print(f"Report: {report_dir / 'pilot_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
