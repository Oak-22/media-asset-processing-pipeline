# Handoff: JPEG-to-RAW Edit Transfer

Read [PLAN-jpeg-to-raw-edit-transfer.md](PLAN-jpeg-to-raw-edit-transfer.md)
first. This note records where the last session stopped.


## Operator Decisions

All decisions were made on 2026-10-01. The first five are already in
the plan; the rest are not yet written into it.

- Working root: `<event>/Photo/RAW Edit Transfer/` on the SSD.
- 9 retouch and mask photos sequestered; the working set is 196.
- The operator imports the ARW copies (Import > Add). The plug-in does
  not import.
- An aggregate summary may go in the repo.
- Branch: build from `main`.
- **Match target, delegated to the agent:** keep RAW advantages. Score
  recovered highlights separately, outside the gates. The pilot picks a
  luminance NR value that roughly matches the JPEG's noise.
- **Tone:** recompute Auto Tone on each RAW, then add the operator's
  manual deltas. Approved.
- **Profile:** Camera Standard. Approved.
- **Pilot:** may create temporary virtual copies of the 6 in-catalog
  pairs (JB106104–JB106109) and render test images to the private root.
  Approved.
- **Results:** put pilot results on the Desktop, or in a new catalog
  collection.


## Where It Stopped

Updated 2026-10-01 (evening). **Pilot run 1 is done; the batch is not
built.** Waiting on the operator's 4 decisions below.

Done this session (branch `agent/jpeg-to-raw-edit-transfer-pilot`, from
`main`, **uncommitted, not pushed**; commit/push waits for the operator):

- Plug-in `lightroom_plugins/jpeg-to-raw-edit-transfer-spike.lrplugin`
  (menu 1 Run pilot, menu 2 Record profile settings). It is installed in
  Lightroom by the operator.
- `scripts/python/stage2/spikes/`: `edit_transfer_metrics.py`,
  `calibrate_edit_transfer_pilot.py` (with `--public-summary`),
  `build_edit_transfer_hash_manifest.py`, `requirements.txt`.
  `tifffile` is installed in `.venv`.
- Tests in `tests/stage2/`, including the Sharma data. 52 tests pass.
- Docs: `docs/future-work/jpeg-to-raw-edit-transfer-spike.md` (findings,
  de-identified) plus index entries. Public aggregate:
  `outputs/lightroom_sdk/lightroom_sdk_jpeg_to_raw_edit_transfer_pilot_summary.json`.
- Private outputs: `<event>/Photo/RAW Edit Transfer/pilot/` holds the
  manifest, 210 renders, the baseline, `profile_reference.json`, and
  `manifests/masters_{pre,post}.json` (IDENTICAL). The per-photo report
  is in `~/Desktop/edit-transfer-pilot-report/`.

Findings (details in the future-work doc):

- **Camera Standard storage, resolved.** The GUI stores only
  `CameraProfile = "Camera Standard"`, with no digest and no Look. The
  plug-in sends a blank digest and `Look = {}`, which reads back
  identically. A leftover Adobe Color Look changes the render, so always
  clear it.
- **Profile.** Adobe Color is closer to the camera JPEG than Camera
  Standard on 6/6 (ΔE00 3.1 vs 4.2). Camera Standard is about +2.2 L*,
  −2 a*, and +3 b* off. After removing the set-wide offset, they are
  about tied. The approved choice of Camera Standard is open again.
- **Tone.** Copying the JPEG values verbatim beats RAW Auto Tone
  (exposure-matched 3.2–3.5 vs 3.9–4.2). The approved method, Auto plus
  deltas, lost. This was confounded by the Camera Standard cast; re-test
  on the chosen profile.
- **WB.** One JPEG temperature increment ≈ −2.5 mired; one JPEG tint
  increment ≈ +0.36 RAW tint (R² 0.99). Measured at 2500 K only.
- **Noise.** Luminance NR ≈ 45 matches the JPEG at ISO 25600.
- **Caveat.** All 6 pairs are the same group shot under the same light.

Open decisions for the operator:

1. Profile: Adobe Color (recommended) or Camera Standard plus a set-wide
   correction.
2. Tone: re-test verbatim, verbatim plus exposure offset, and Auto plus
   deltas on that profile.
3. Run 2 sample: copy the card and import first, then pilot about 12
   varied frames (stage, candid, WB extremes, HSL). The alternative is to
   re-run on the same 6.
4. Luminance NR: about 45 (match), 25–30 (more detail), or manual
   Denoise.

Fast path the operator was offered: "go with defaults" (Adobe Color,
verbatim tone, P4 WB conversion, NR 45). Then build the card copy,
recipe export, translation, dry run, apply, and restore, which is about
1.5–2 h of agent work.

Notes from the session:

- The operator once set Camera Standard on JB106106 "Copy 1" (the v01
  deliverable) by mistake. They reverted it to Adobe Color, and the
  settings match v01 except that `CameraProfileDigest` was dropped (the
  render is identical).
- 6 ARW "Edit Transfer Pilot" virtual copies also landed in the
  operator's `5. jpeg-to-… > v01` collection. All pilot copies are in
  collection "Edit Transfer Pilot", for the operator to remove later.
- The pilot's per-render export sessions make a "2 operations"
  progress flicker. Run 2 should export one variant for all pairs per
  session.
- Lightroom's memory had grown to 12 GB after 31 h. Suggest a restart
  before long runs.


## Files Worth Keeping

The session scratchpad will be cleared. Copies of its key files are in
`~/Desktop/edit-transfer-handoff-scratch/`:

- `analysis/`: catalog settings for v01, EXIF for the card and SSD, and
  the Lua-table parser.
- `research_digest.txt`: SDK, translation, and validation findings with
  evidence.
- `colormetrics.py`, `align.py`, `ciede2000testdata.txt`, `dcp.py`:
  prototypes.

Re-snapshot the catalog read-only if needed: copy `JB_Master_v2.lrcat`
and its `-wal` file, and open the copy with `?mode=ro`.


## Standing Rules

- Never add, remove, or reload Lightroom plug-ins; hand the operator the
  `.lrplugin` path.
- Never write to JPEG masters or the original event folder.
- Keep client paths and names out of git: use `<event>`, `<SSD>`, and
  `<card>`. This handoff file is untracked; do not commit it.
- The SD card is mounted read-only (lock switch on). The 205 ARWs are in
  `DCIM/10560926`.
