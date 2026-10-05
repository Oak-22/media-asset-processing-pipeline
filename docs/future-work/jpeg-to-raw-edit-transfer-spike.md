# JPEG to RAW Edit Transfer Spike

## Purpose

This spike tests whether per-photo Develop edits made on camera JPEGs
can be moved onto the matching RAWs, through the Lightroom SDK, without
touching the originals. It is Spike B ("apply a global recipe without
damaging existing state") of
[Lightroom Edit Recipe Execution Boundary](lightroom-edit-recipe-execution-boundary.md).

The source is one event shot RAW + JPEG on a Sony a7R III. The operator
edited the camera JPEGs as virtual copies, with global adjustments only.
Those edits exist only in the catalog. The target is to give each RAW
the same edit while keeping the RAW's advantages (highlight detail, its
own noise reduction).

The chosen route reads each edit's exact slider values through the SDK,
translates the groups that mean something different on a RAW (profile,
white balance, tone), and applies them with `photo:applyDevelopSettings`.
Fitting sliders from rendered pixels was rejected: the JPEGs are
clipped and tone-mapped, and several sliders produce near-identical
pixels, so the values cannot be recovered that way.


## Pilot

Before any batch run, a calibration pilot runs on the 6 RAW + JPEG pairs
that were already in the catalog. Code:

- [`jpeg-to-raw-edit-transfer-spike.lrplugin`](../../lightroom_plugins/jpeg-to-raw-edit-transfer-spike.lrplugin/README.md)
  makes temporary virtual copies, applies variants, exports 16-bit TIFF
  renders, and reads settings back.
- [`calibrate_edit_transfer_pilot.py`](../../scripts/python/stage2/spikes/calibrate_edit_transfer_pilot.py)
  aligns and scores the renders (CIEDE2000, checked against Sharma's
  published test pairs) and writes a private per-photo report.
- [`build_edit_transfer_hash_manifest.py`](../../scripts/python/stage2/spikes/build_edit_transfer_hash_manifest.py)
  hashes the masters and sidecars before and after.

Renders and per-photo reports stay in a private working root next to
the originals. The repository keeps only the aggregate summary:
[`lightroom_sdk_jpeg_to_raw_edit_transfer_pilot_summary.json`](../../outputs/lightroom_sdk/lightroom_sdk_jpeg_to_raw_edit_transfer_pilot_summary.json).


## Run 1 Findings (2026-10-01, Lightroom Classic 15.1)

6 pairs, 210 renders, 0 errors. All 18 master files (ARW, JPEG, XMP)
were byte-identical before and after (SHA-256).

**Caveat.** The 6 pairs are frames of one group shot under one light.
Agreement across them is not independent evidence that the calibration
holds across the event.

| Gate | Scored | Finding |
|---|---|---|
| P1 determinism | PASS | Repeat export max ΔE00 0.029 |
| P2 identity | PASS | A RAW edit's settings on a fresh copy of the same RAW render identically (mean ΔE00 0.000). `RetouchAreas` differs as data but not in pixels |
| P3 base profile | FAIL | Adobe Color, not Camera Standard, is closest to the camera JPEG (6 of 6) |
| P4 WB scale | PASS | Linear and consistent (R² ≥ 0.99) |
| P5 tone method | FAIL | Copying the JPEG values beats re-running Auto Tone; confounded by the profile cast |
| P7 SDK mechanics | FAIL as scored | Mechanics work; both failures are benign (below) |


### Profile

Against the camera JPEG, unclipped pixels, after alignment:

| Profile | median ΔE00 | mean ΔL* | mean Δa* | mean Δb* |
|---|---|---|---|---|
| Adobe Color | 3.0–3.3 | ≈ 0 | +1.4…+1.8 | +0.9…+1.3 |
| Camera Standard | 4.2–4.4 | +2.1…+2.3 | −1.8…−2.1 | +2.8…+3.3 |
| Camera Neutral | 4.0–4.2 | +2.2…+2.4 | −2.5…−2.8 | −0.9…−0.3 |

The measurement floor (Lightroom's render of the JPEG at zero settings
vs an independent decode) is ΔE00 1.1. Camera Standard renders brighter
and green-yellow relative to the Sony JPEG. After removing a set-wide
brightness and colour offset, Camera Standard and Adobe Color are about
tied (ΔE00 ≈ 2.6 vs 2.5 with noise averaged out). Without that offset,
Adobe Color is clearly closer. The operator's earlier choice of Camera
Standard is therefore open again.

**How Lightroom stores Camera Standard.** The Profile Browser stores it as
`CameraProfile = "Camera Standard"` with no `CameraProfileDigest` and no
`Look`. `applyDevelopSettings` merges keys and cannot delete them. But
sending the name with a blank digest and an empty `Look` reads back in
that same canonical form. A leftover Adobe Color `Look` does not replace
the profile, but it still changes the render (ΔE00 1.4), so it must be
cleared explicitly.


### White Balance

The JPEG's relative WB scale maps linearly onto the RAW's:

- one JPEG temperature increment ≈ −2.5 mired (warmer);
- one JPEG tint increment ≈ +0.36 RAW tint.

The fits have R² ≥ 0.99, and per-pair slopes agree within 2%. These were
measured at one light (As Shot 2500 K) and still need a check across the
event's other lighting.


### Tone

Measured against the edited JPEG, all on Camera Standard with As Shot WB:

| Method | median ΔE00 | exposure-matched | \|ΔL* p50\| |
|---|---|---|---|
| JPEG values copied verbatim | 3.9–4.3 | 3.2–3.5 | 2.1–2.8 |
| Auto Tone recomputed on the RAW | 3.9–4.9 | 3.9–4.2 | 0.2–3.1 |
| JPEG values + set-wide offset | 4.4–4.9 | 3.6–3.8 | 3.2–3.9 |

Auto Tone on the RAW pulls Highlights 15–41 lower and Shadows 10–22
higher than Auto Tone on the JPEG. Copying the JPEG values gives the
closest tone shape. Its remaining error is mostly a brightness offset,
and the Camera Standard profile itself accounts for about +2.2 L* of it.
The planned method (recompute Auto, add the operator's deltas) did not
win. Tone should be re-tested on the chosen profile.


### SDK Mechanics

- `applyDevelopSettings({AutoTone = true}, name, true)` resolves Auto
  Tone immediately. It also rewrites the legacy PV2010 keys `Brightness`,
  `Contrast`, `Exposure`, and `Shadows`, which have no effect under
  Process Version 15.4.
- Partial applies change only the keys sent.
- Restoring the starting settings is exact, except for keys the pilot
  added, which cannot be deleted (`CropConstrainAspectRatio` here).
- `catalog:createVirtualCopies` acts on the current selection. The
  masters must be visible in the active source, and the master's
  `virtualCopies` metadata can lag a fresh copy. The plug-in looks copies
  up through the masters' folder instead.


### Noise

At ISO 25600, about Luminance NR 45 (range 36–48) matches the JPEG's
in-camera noise reduction, measured on a central crop. Whether to match
it or keep more detail is an operator decision.


## Next Decision

Before the batch, the operator decides:

1. **Profile:** Adobe Color, or Camera Standard with a set-wide correction.
2. **Tone method:** re-tested on that profile.
3. **Sample for run 2:** varied frames from the imported ARWs (stage,
   candid, WB extremes, HSL edits), rather than one repeated group shot.
4. **Luminance NR level.**

Pilot run 2 should also export one variant across all pairs per session.
Per-render export sessions show a flickering second progress task in
Lightroom's activity center.


## Boundary

The pilot calibrates the transfer. It does not export recipes, apply
them to imported RAWs, or claim that a RAW will match its JPEG pixel for
pixel. Retouch, Generative Remove, and AI-mask edits are out of scope
for this batch.
