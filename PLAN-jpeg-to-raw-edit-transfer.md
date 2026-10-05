# Plan: JPEG-to-RAW Edit Transfer


## Context

The operator finished the final cull of one event and edited it in
Lightroom Classic: 206 photos, global adjustments only (by intent). 205
were edited as camera JPEGs. One, the whole-class group photo, was
edited as a RAW. Every JPEG has a matching Sony ARW from the same
shutter actuation (the camera shot RAW + JPEG).

Goal: give each RAW the same look as its edited JPEG, by reproducing
the operator's per-photo Develop settings on the RAWs through a
Lightroom Classic Lua plug-in. Originals stay untouched, and outputs go
to a new location.

This is Spike B ("apply a global recipe without damaging existing
state") at Level 1 of
[Lightroom Edit Recipe Execution Boundary](docs/future-work/lightroom-edit-recipe-execution-boundary.md).
Spike A (read settings through the SDK) is already shown by
[`develop-settings-export-test-spike.lrplugin`](lightroom_plugins/develop-settings-export-test-spike.lrplugin/README.md),
and `photo:applyDevelopSettings` is already proven in
[`crop-auto-vs-upright-level-spike.lrplugin`](lightroom_plugins/crop-auto-vs-upright-level-spike.lrplugin/README.md).

Privacy note: this repo is public and root `PLAN-*.md` files are not
git-ignored. The event, its folder names, and absolute paths are written
here as `<event>`, `<SSD>`, and `<card>`.


## Status

Plan only. Nothing is built.

Decisions made with the operator (2026-10-01):

- **Working root.** Use the private working root below, next to the
  originals.
- **Sequester the 9 exception photos.** These are the 7 Generative
  Remove photos, the heal photo, and the masked photo. They are left out
  of the batch and handled in a later pass. The **working set is 196
  JPEG edits** (205 − 9). The group RAW stays as the identity control.
- **Import.** The operator imports the ARW copies with Lightroom's
  Import > Add. The plug-in does not import.
- **Public evidence.** An aggregate, de-identified validation summary
  may be committed to the repo.
- **Branch.** Either works; build from `main`.

Everything under "Observed" was inspected
read-only on 2026-10-01. Sources: a copied snapshot of the catalog, the
event folder on the SSD, the SD card (mounted read-only, lock switch
on), and the LrC 15.1 app bundle. Research findings marked
*needs pilot* are settled by the pilot in step 5, not assumed.


### Observed: The Set and Its Files

**The set.** It is the catalog collection `v01` under
`<event> > 3. Deliverables` (206 photos). All 206 are **virtual
copies** (`Copy 1`). 205 have JPEG masters and 1 has an ARW master
(the group photo).

**Where the edits live.** Lightroom never writes virtual-copy Develop
settings to XMP. The XMP embedded in the JPEG files holds only the
masters' state. The catalog, read through `getDevelopSettings()`, is
the only source of the edits. XMP sidecars cannot be used for approach
(a).

**Pairing.** It is complete. All 205 JPEG masters pair 1:1 with an ARW
on the card (`<card>/DCIM/10560926/`). Every pair agrees on file name,
`ShutterCount`, `DateTimeOriginal`, and camera `InternalSerialNumber`,
with 0 unmatched and 0 ambiguous. No two photos share a capture second.
The 205 ARWs are about 9.5 GB. Only 6 event ARWs are on the SSD and in
the catalog (`JB106104`–`JB106109`, each with its JPEG).

**Camera.** Sony a7R III, Tamron 35-150mm F2-2.8. The JPEG is size M
(5168×3448), a downscale of the same frame Lightroom shows for the ARW
(7952×5304). The aspect ratio differs by 0.03%, and EXIF orientation
matches on all 205 pairs (19 portrait).

**JPEG rendering.** The JPEG is Creative Style Standard with DRO Off and
sRGB. exiftool's "PP2" label is how it names Creative Style Standard;
it is not a video picture profile. In-camera distortion, vignetting,
and CA correction are baked in. Adobe ships a RAW lens profile for this
lens but no JPEG one, so the JPEG edits had no extra lens correction.

**Noise and clipping.** High ISO: 107 photos at ISO 32000. The JPEG has
in-camera noise reduction; a RAW at Lightroom defaults will look
noticeably noisier. Clipping: in the median JPEG, 18% of pixels have at
least one channel ≥ 250, and 96 photos exceed 20%. The RAW holds
highlight detail there that the JPEG lost.

**Lightroom state.** Lightroom Classic 15.1 (Camera Raw 18.1, Process
Version 15.4). XMP auto-write is on, so Lightroom writes XMP into JPEG
files and `.xmp` next to RAWs. A card insert opens the Import dialog.


### Observed: What the Edits Contain

**Tone is mostly Auto Tone.** All 205 JPEGs were imported with an
"Auto Tone" import preset. On 172 of 205, the virtual copy's
Exposure/Contrast/Highlights/Shadows/Whites/Blacks/Vibrance/Saturation
equal Auto Tone's values exactly. On 33, the operator tweaked on top of
Auto, for example Exposure −0.34…+0.20 and Highlights −74…+37.

**White balance.** `Custom` on 116, `As Shot` on 89. The Custom values
are on the relative JPEG scale (`IncrementalTemperature` −12…+11,
`IncrementalTint` −12…+19), not Kelvin.

**Other groups:**

- **Crop.** On nearly all photos; `CropAngle` −3.67°…+3.85° on 200.
- **HSL.** On 8 photos (desaturating Red/Orange/Yellow, Magenta,
  Aqua/Blue).
- **B&W.** 1 photo.
- **Unused.** Tone curve (Linear on all), Texture, Clarity, Dehaze.

**Detail values.** Sharpness 40 and Color NR 25 came from the import
preset and equal Lightroom's RAW defaults. They were not per-photo
choices.

**Exceptions to "global-only":**

| Edit | Photos | Transferable? |
|---|---|---|
| Generative Remove (Firefly) | 7 | No. The fill is tied to the JPEG's pixels and cannot be regenerated through the SDK |
| Classic heal or clone | 1 | Likely; normalized coordinates land on the same content (pilot) |
| AI Facial Skin mask (Texture −16, Sharpness +53) | 1 | Possibly, through `photo:updateAISettings()` (pilot) |
| Retouch on the group RAW | 1 | Not needed; already on the RAW |

**Group photo.** Already a RAW edit. Its effective profile is
**Adobe Color**, stored as `Adobe Standard` plus an Adobe Color `Look`.
No transfer is needed. It serves as the identity control in validation.


## 1. Feasibility: Approach (a) vs (b)


### Comparison

| | (a) Read settings from the catalog through the SDK | (b) Estimate edits by diffing the edited JPEG vs a RAW render |
|---|---|---|
| Input exists? | Yes, all 206; complete values, no pending-Auto placeholders | Needs Lightroom renders of every RAW and edited JPEG |
| Recovers the operator's intent | Exactly, at the slider level, including which values were Auto Tone and which were manual | No, only an approximation of the output pixels |
| Crop and straighten | Exact normalized values | Must be estimated by image registration |
| Cost | One SDK read pass (seconds) | About 70–600 Lightroom renders per photo, so 20k–120k renders for the set |
| Main error source | JPEG and RAW start from different base renders | Everything in (a), plus fitting error |

**Recommendation: (a).** Read the exact per-photo settings, translate
the groups whose meaning differs between JPEG and RAW (WB, profile,
tone), and apply them. Use (b)-style render comparison only for three
jobs:

- **Base calibration.** Choose the profile, and find any set-wide
  exposure or WB offset.
- **WB calibration.** Find the conversion from the JPEG's relative WB
  scale to Kelvin and Tint.
- **Validation.**


### Where (b) breaks down

- **Lost information.** The JPEG edit was applied to an 8-bit,
  gamma-encoded, tone-mapped camera render with in-camera NR. It is
  heavily clipped (median 18% of pixels). Clipped and quantized data
  cannot be inverted, so the slider values cannot be recovered exactly.
- **Sliders are not identifiable.** Exposure, Contrast, Highlights,
  Shadows, Whites, and Blacks all reshape one tone response, so many
  combinations give near-identical pixels. Highlights and Shadows adapt
  locally, so no per-pixel curve or histogram fit captures them.
  Vibrance depends on saturation. An HSL band is only observable when
  its hue is in the frame.
- **Geometry is entangled.** Crop and straighten must be estimated
  together with the difference between in-camera and Lightroom lens
  correction.
- **The rendering math is proprietary.** Fitting needs Lightroom in the
  loop, at roughly 70–600 renders per photo.
- **The result can't be applied.** A fitted per-photo pixel transform,
  such as a 3D LUT, has no SDK entry point. The only route is installing
  205 custom profiles, and those act before the Basic panel, which is
  the wrong stage.


### What still limits (a)

- **Base render.** The JPEG edits sit on Sony's Standard rendering. The
  closest RAW base is Adobe's **Camera Standard** profile, which is
  built to match it. A residual hue and tone difference remains.
- **White balance units.** JPEG WB is relative; RAW WB is Kelvin plus
  Tint. Adobe documents no conversion. Lightroom's own JPEG-to-RAW WB
  copy gives inconsistent results depending on the path used. So the
  plug-in computes the RAW values itself: the RAW's As Shot WB plus a
  shift calibrated in the pilot.
- **Tone on RAW headroom.** On the 6 pairs that already exist in the
  catalog, RAW Auto Tone differs from JPEG Auto Tone by about −20
  Highlights and +15 Shadows. Copying JPEG numbers verbatim would
  leave RAW highlights too bright and shadows too dark.
- **Clipped highlights.** Where the JPEG clipped, the RAW will show
  detail. Matching the JPEG exactly there would mean throwing that
  detail away.
- **Noise.** The JPEG's in-camera NR has no slider equivalent. The RAW
  needs its own NR decision.


## 2. Design (proposed)


### Flow

```text
0. Hash manifest of the original event folder (pre)          [Python, read-only]
1. Copy 205 ARWs: card -> private working root, SHA-256       [Python, card read-only]
2. Export edit recipes from v01 (getDevelopSettings)         [plug-in, read-only]
3. Pair + translate -> per-photo RAW recipe; mark the 9       [Python]
   sequestered photos "deferred"
4. Operator imports the ARW copies (Import > Add) into       [operator]
   a new collection
5. Pilot: calibrate profile, WB, tone method, geometry        [plug-in + Python]
   -> operator go/no-go
6. Dry run on the 196-photo working set                       [plug-in, no writes]
7. Apply on the 196 + read-back verification + log            [plug-in]
8. Validation: render error report                            [Lightroom export + Python]
9. Hash manifest of the original event folder (post); must match step 0
```

The pilot can start before step 1. Its WB, profile, and tone
calibration runs on the 6 JPEG+ARW pairs already in the catalog. Those
runs use temporary virtual copies, so the masters are not changed.


### Private working root

All per-photo outputs stay off git:

```text
<SSD>/JB Photography/<event>/Photo/RAW Edit Transfer/
  RAW/                 205 ARW copies (+ .xmp that Lightroom auto-writes here)
  recipes/             exported JPEG recipes, translated RAW recipes
  logs/                dry-run plan, apply log, pre-apply settings (rollback)
  manifests/           card-copy manifest, pre/post hash manifests
  renders/             validation TIFFs (baseline / edited, JPEG and RAW sides)
  validation/          per-photo error JSON, summary, side-by-side sheets
```

Copying the ARWs into their own folder serves three purposes:

- The original `Photo/RAW/` folder stays byte-identical.
- Lightroom's auto-written `.xmp` sidecars land only next to the copies.
- Undoing everything means removing one folder and one collection.

The Python scripts refuse any output path inside the git checkout.


### Step 3: Translation rules

Python builds an explicit **whitelist** recipe per photo. This matters
because `applyDevelopSettings` merges whatever keys it is given into
the photo's settings with no validation. A JPEG-only key such as
`CameraProfile = "Embedded"` or `IncrementalTemperature` would be
stored silently on the RAW.

| Key group | Action | Rule |
|---|---|---|
| Tone + presence (Exposure, Contrast, Highlights, Shadows, Whites, Blacks, Vibrance, Saturation) | translate | **Primary:** run Auto Tone on the RAW (after profile, WB, and lens are set), then add the operator's manual delta (virtual copy minus the JPEG master's Auto value; non-zero on 33 photos). **Fallback** if the pilot prefers it: copy the JPEG values plus a set-wide offset (≈ Highlights −20, Shadows +15, Whites +4, Blacks −4, from the 6 in-catalog pairs) |
| White balance | translate | Custom: RAW As Shot plus a linear shift in mired and tint per JPEG increment, with constants from the pilot. Send `WhiteBalance = "Custom"`, `Temperature`, `Tint`, `CustomTemperature`, and `CustomTint`. As Shot: send `WhiteBalance = "As Shot"` only (plus a set-wide offset if the pilot finds one) |
| Profile | set fixed | **Camera Standard**, set explicitly, with the Adobe Color `Look` cleared (pilot confirms how this is stored) |
| Crop, CropAngle, CropConstrainAspectRatio | copy | Normalized to the same frame; the pilot checks residual lens-geometry offset |
| HSL, B&W (`ConvertToGrayscale` + mix), tone curves | copy | Same controls; the 8 HSL photos and the B&W photo get a visual review |
| Lens | set fixed | Adobe lens profile on (`LensDefaults`, 100/100), Remove Chromatic Aberration on. This matches the in-camera correction baked into the JPEG |
| Sharpening, color NR | keep RAW defaults | Same numbers as the JPEG edits already |
| Luminance NR | operator decision | Leave at 0, set a fixed value, or run Denoise by hand; see Open Questions |
| Generative Remove (7), classic heal (1), AI mask (1) | deferred | These 9 photos are sequestered and get no recipe in this batch. They are listed in the dry-run log and handled in a later pass |
| `Preset`, `AutoToneDigest*`, `CameraProfile = "Embedded"` with its digest, `Incremental*`, `CustomIncremental*`, `orientation`, `Version`, `ProcessVersion`, legacy PV2010 keys, `GrainSeed`, `ToggleStyle*`, `FilterList`, `EnableDistractionRemoval` | exclude | JPEG-only or bookkeeping |

Every recipe row records `source_value`, `applied_value`, and `rule`,
so the log shows what was copied, translated, recomputed, or left out,
and why.


### Steps 2, 4, 6, 7: The plug-in

New plug-in: `lightroom_plugins/jpeg-to-raw-edit-transfer-spike.lrplugin`

**Menu items** (Library > Plug-in Extras):

1. Export edit recipes (selected)
2. Apply RAW recipes – dry run (selected)
3. Apply RAW recipes (selected)
4. Restore pre-apply settings (selected)
5. Render validation pairs (selected)

**Read side.** Every source photo must be a virtual copy with a JPEG
master. The plug-in never opens a write gate on source photos. This
matters because any master-level write would rewrite the JPEG file
itself under XMP auto-write.

**Import (operator).** The operator imports
`RAW Edit Transfer/RAW/` with Import > Add (no move or copy) into a new
collection such as `v01 – RAW`. The import should not apply a Develop
preset. If the Auto Tone import preset is applied anyway, the plug-in
recomputes Auto after setting the profile, so the result is the same.

**Matching.** Recipe rows are keyed by the virtual copy's `uuid`. Each
target RAW is matched by path, file name, and capture time. Ambiguous or
missing matches are skipped and listed.

**Guard.** Apply runs only on RAW masters inside the private
`RAW Edit Transfer/RAW/` folder. It refuses JPEG masters, virtual
copies, and any photo outside that folder.

**Dry run.** It opens no write gates. Per photo, it records:

- source JPEG values, the master's Auto values, and the operator's
  deltas;
- the RAW's As Shot WB and the computed WB;
- the planned payload and its diff against current settings;
- excluded keys with reasons, and review flags.

**Apply.** Batches of about 25 photos per gate. In each gate, per photo:

1. `createDevelopSnapshot("pre-transfer v01")`
2. `applyDevelopSettings(recipe, "JPEG edit transfer v01")`
3. `createDevelopSnapshot("transfer v01")`

After each gate, it reads the settings back and records expected vs
actual per key. The run is cancelable between batches and idempotent.
The pre-apply settings are also saved to `logs/` for **Restore**.

**Auto Tone.** Applying Auto Tone needs a separate step: set the base
settings, trigger Auto, read the resolved values, then apply the deltas.
The SDK mechanics for this are a pilot item.

**No presets.** Values differ per photo (90 distinct Exposure values, a
unique crop on nearly every photo). Also, Adobe has confirmed a LrC 15.x
bug where applying a plug-in-created preset to RAWs can reset WB to
2000 K. Per-photo `applyDevelopSettings` avoids both issues.

**Code base:**

- Copy of `SpikeCommon.lua`'s ordered JSON writer, plus a sorted-key
  fallback for plain maps. Today those are written as `[]`, which would
  silently drop Develop settings tables.
- Vendored `rxi/json.lua` (MIT) to read recipes.
- The apply, read-back, and progress pattern of `ProbeUprightLevel.lua`.
- `LrLogger` output to Lightroom's log folder.


### Step 5: Pilot (gate before the batch)

| # | Settles | Pass rule |
|---|---|---|
| P1 | Render determinism and the measurement floor (the same photo exported twice) | max ΔE00 ≤ 0.05 |
| P2 | Identity control: the group photo's settings on a copy of its ARW | mean ΔE00 ≤ 0.3; any keys that do not round-trip are listed |
| P3 | Base profile: Camera Standard vs Adobe Color vs Camera Neutral, against the original camera JPEG file | the chosen profile has the lowest median ΔE00 on ≥ 5 of 6 pairs, and ≤ 3 |
| P4 | WB scale: renders at known Kelvin/Tint offsets vs JPEG increments | linear fit R² ≥ 0.95, slopes agree within ±20%; predicts the group photo's own WB within ±50 K / ±2 Tint |
| P5 | Tone method: Auto Tone + deltas vs copy + offset | the lower median ΔE00 wins; must reach \|ΔL\* p50\| ≤ 2 |
| P6 | Geometry: crops and lens correction | \|scale − 1\| ≤ 0.3%, shift ≤ 0.2% of width, corner bias ≤ 0.15 EV |
| P7 | SDK mechanics: profile set with no leftover Look, Auto Tone resolves, partial apply leaves other keys unchanged, Restore works | read-back matches exactly |

P1–P5 and P7 run on the 6 in-catalog pairs, using temporary virtual
copies and small renders written to the private root. P6 runs after the
import. Results go to the operator for go or no-go before the
batch.


## 3. Validation


### Method

**Sample.** 26 photos, chosen by parameter extremes and clipping:

- WB increments at both extremes
- Exposure −1.27 and +0.83
- The one photo at Highlights −100
- Shadows and Whites extremes
- Portrait photos
- High-clipping photos
- The 8 HSL photos (sampled)
- The B&W photo
- The group RAW, as the identity control

The 9 sequestered photos are not in this sample. Metrics run on all 196
working-set photos plus the group RAW. Human review covers the 26, plus the 5
worst.

**Renders.** One `LrExportSession` setting for every render: 16-bit
TIFF, uncompressed, sRGB, long edge 2048, no output sharpening, no
watermark, copyright-only metadata, no re-import. Output goes to
`renders/` in the private root.

**JPEG baseline.** The camera JPEG file itself, decoded with `sips`.
The JPEG master in the catalog is not a neutral baseline, because it
carries Auto Tone.

**Error decomposition.** From the floor up:

| Pair | What it isolates |
|---|---|
| Same RAW exported twice | Render noise floor |
| Group photo: its settings on a copy of its ARW | Identity (round-trip) |
| Camera JPEG vs RAW with base settings only | Base-rendering mismatch |
| Edited JPEG virtual copy vs RAW with recipe | Total error (the headline number) |

`transfer_excess` is the total mean ΔE00 minus the base mean ΔE00. It
separates translation error from base-rendering error.

**Alignment.** Downsample to 1024 px. Register with a similarity
transform (phase correlation on gradient magnitude, with a rotation
prior from `CropAngle`). Trim 4% of the borders, and check the residual
shift on a 4×4 tile grid.

**Clip mask.** Pixels that clipped in the camera JPEG (any channel
≥ 250, dilated by 2 px) are reported separately and kept out of the
gates. The RAW is expected to differ there.


### Metrics

Metrics are reported per photo, never only as an average:

| Metric | Detects | PASS | FAIL |
|---|---|---|---|
| ΔE00 mean / median / p95 (unclipped) | Overall look difference | mean ≤ 2.0, p95 ≤ 6 | mean > 3.5 |
| Mean ΔL\* | Brightness bias (2 ≈ 1/8 stop) | \|ΔL\*\| ≤ 2 | > 4 |
| Mean Δa\*, Δb\* | Color cast (Δb\* 1.5 ≈ 7 mired) | ≤ 1.5 | > 3 |
| L\* p5 / p50 / p95 differences | Tone shape (shadows, highlights) | reported | — |
| Gradient correlation, tile residual | Crop or alignment error | ≥ 0.95, ≤ 1 px | alignment failure |
| Clip-region ΔL\* | Recovered highlights (expected negative) | reported | — |

Anything between PASS and FAIL is REVIEW. Known-risk photos (HSL, B&W,
> 30% clipped) are always REVIEW.

**Implementation.** Python with numpy plus `tifffile` (one pinned
dependency). ΔE2000 is checked against Sharma's 34 published test
pairs. The tests use synthetic data only.

**Report.** One JSON record per photo, holding settings hash,
alignment, coverage, base and edited metrics, `transfer_excess`,
verdict, and reasons. Also a summary and side-by-side review sheets,
all in the private root. An aggregate, de-identified summary (counts,
metric distributions, no paths or images) goes to
`outputs/lightroom_sdk/lightroom_sdk_jpeg_to_raw_edit_transfer_summary.json`.


## Files to Add or Change

**Code:**

- `lightroom_plugins/jpeg-to-raw-edit-transfer-spike.lrplugin/`, made
  up of:
  - `Info.lua`
  - `TransferCommon.lua`
  - `json.lua` (rxi, MIT)
  - `ExportRecipes.lua`
  - `ApplyRecipes.lua` (dry run and apply)
  - `RestorePreApply.lua`
  - `RenderValidationPairs.lua`
  - `README.md` (install, run, boundary)
- `scripts/python/stage2/spikes/`:
  - `copy_card_raws_for_edit_transfer.py`: reuses
    `stage0.transfer.copy_verified`, `sha256_file`, and
    `preflight_collisions`. It does **not** run the Stage 0 orchestrator
    or write its ledger.
  - `pair_and_translate_edit_recipes.py`
  - `build_edit_transfer_hash_manifest.py`: the ADR 0004 pattern with an
    extension filter.
  - `calibrate_edit_transfer_pilot.py`
  - `measure_edit_transfer_render_error.py`
  - `requirements.txt` (`numpy`, `tifffile`)
- `tests/`: pairing, recipe whitelist, WB mapping, ΔE2000 (Sharma
  data), and alignment recovery, all on synthetic fixtures.

**Docs:**

- `docs/future-work/jpeg-to-raw-edit-transfer-spike.md`, which does not
  name the event.
- Index entries in `docs/future-work/README.md` and
  `scripts/python/README.md`.
- A refresh of the boundary doc's "Future Implementation Shape" paths.


## Risks

- **Wrong WB conversion.** It gives a plausible but wrong cast on every
  Custom-WB photo. The P4 gate and the Δa\*/Δb\* metric exist to catch
  this.
- **Auto Tone on the RAW may not match the JPEG's Auto.** Auto Tone
  responds to different data on the RAW. The P5 pilot compares it with
  the copy + offset method before committing.
- **Base mismatch.** Camera Standard is the closest match, but it will
  not be pixel-identical. The likely residual is in skin tones and
  saturated stage colors.
- **Highlights and noise.** RAWs will show highlight detail and noise
  that the JPEGs did not. This is a policy question, not a bug (see Open
  Questions).
- **Wrong target.** Applying to the wrong photos would rewrite Develop
  state. These bound the risk: the target guard, dry run, named history
  step, snapshots, saved pre-apply settings, and pre/post hash
  manifests.
- **Privacy.** A stray `git add -A` could commit private outputs.
  Nothing per-photo is written inside the repo tree.


## Boundaries

This plan does not claim:

- pixel-identical output (JPEG and RAW start from different renders);
- any transfer for the 9 sequestered retouch and mask photos in this
  batch;
- that approach (b) can recover slider values.

It aims to reproduce the operator's per-photo intent on the RAWs, with
a measured, per-photo error.

Lightroom plug-ins are added and reloaded by the operator only. The
agent prepares the `.lrplugin` folder and hands over its path.


## Open Questions for the Operator

1. **Match target.** Should the RAW match the edited JPEG as closely as
   possible, including clipped highlights and the JPEG's noise level?
   Or should it carry the same edit while keeping RAW advantages (more
   highlight detail, your own NR or Denoise)? This decides NR and how
   clipped areas are scored.
2. **Tone.** Is it OK to recompute Auto Tone on each RAW and re-apply
   your manual tweaks on top, instead of copying the JPEG numbers? The
   pilot will compare both methods.
3. **Profile.** Is it OK to use Camera Standard instead of Lightroom's
   default Adobe Color?
4. **Pilot copies.** For the pilot, may the plug-in create temporary
   virtual copies of the 6 in-catalog pairs and export small test
   renders to the private root?


## Next Step

Wait for the operator's go-ahead and answers to the open questions.
Then build in this order:

1. Pilot on the 6 in-catalog pairs, then report results and wait for go
   or no-go
2. Card copy
3. Recipe export
4. Translation
5. Operator imports the ARW copies
6. Dry run on the 196-photo working set
7. Apply
8. Validation report
