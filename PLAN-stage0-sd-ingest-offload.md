# Plan: Stage 0 – SD Card Ingest and Semantic Offload

## Context

Today, getting a shoot off the Sony SD card and onto the Samsung 990 Pro SSD is manual: plug in, make folders by hand under `JB Photography/…`, drag files, hope nothing was missed. Folder naming has drifted as a result (`RAW/Photo` vs `Photo/RAW`, en dash vs em dash, a `(Dup)` Nascar folder, `RAW (MISSING)`).

Goal: when an SD card is inserted **and** the Samsung SSD is mounted, automatically inventory the card, split it into shoots, classify each shoot on-device (Apple Vision), ask the operator **only** what cannot be inferred (client name, personal vs client, etc.) through a short series of macOS dialogs, then scaffold the folder in the existing taxonomy, copy with hash verification, and emit a manifest.

This becomes **Stage 0** of this repo: it sits upstream of Stage 1 (Lightroom import) and follows the repo's existing patterns — deterministic orchestration around uncertain inputs, probabilistic output bounded by human review, hash-manifested checkpoints (ADR 0004).

Decisions already made with the user:
- Lives in this repo as Stage 0.
- Classifier: Apple Vision on-device (via pyobjc), one classification per shoot using a sample of frames.
- New-shoot layout: `<Shoot>/Photo/{RAW,Exports}` + `<Shoot>/Video/{RAW,Exports}` (DJ Alx style).
- Confirmation: macOS dialog questionnaire — automate everything possible, ask only for the rest.

## Observed environment (inspected, read-only)

- SSD volume: `/Volumes/Samsung 990 Pro NVMe M.2 SSD` (APFS, disk7s1). Photo root: `JB Photography/`.
- Taxonomy (top level): `Animals, Architecture, Automotive, Culinary, Landscape, People, Real Estate, Social Media, Sports, Travel` (+ ignored: `*.lrdata`, `__LrC Catalog Archive`).
- `People/` is deep: `Personal/{Family,Friends,Personal Projects}` and `Client Work — SSD/{Commercial,Events,Weddings & Engagements}/<sub>/<client>/<session>`, e.g. `Events/Education/Graduation — SSD/High School/Melliah Davis/Photo/RAW`, `Commercial/Brand Photography/DJ Alx/Mangos 2026/Photo/RAW`.
- Shoot names: `<Subject> – <Descriptor> – <Location>` with en dash (`Brandy – Modeling – Outdoors`, `Nascar – Sonoma, CA`, `Lake Tahoe – Eastons Family`); repeat clients get a client folder with `<Session> <Year>` children.
- Camera files: `JB######.ARW` (+ JPG, XMP), video as `MP4` + `XML` (Sony `PRIVATE/M4ROOT/CLIP` layout).
- Tooling: `exiftool` (Homebrew), Python 3.14. Existing launchd agents use the `com.jbphoto.*` label style (`~/Library/LaunchAgents/com.jbphoto.pathwatch.plist`).

## Design

### Pipeline flow (one run per card insert)

```text
launchd (StartOnMount)
  → 1. detect: SD card present? (DCIM/ + Sony layout)   SSD present? (by volume UUID)
        └─ SSD missing → notification "Plug in Samsung SSD", exit (re-fires on next mount)
  → 2. inventory: exiftool -json over card → capture time, model, GPS, file type
        └─ drop files already in the offload ledger (card reinsert is a no-op)
  → 3. segment: split into shoots by capture-time gap (default 3 h) + date change
  → 4. classify (per shoot): sample ≤12 frames, extract embedded JPEG preview
        (exiftool -b -PreviewImage, no RAW decode), run Vision
        VNClassifyImageRequest + VNDetectFaceRectanglesRequest + VNDetectHumanRectanglesRequest
        → aggregate label scores → map to taxonomy via config → ranked candidates
        + reverse-geocode GPS if present (CLGeocoder via pyobjc) → location string
  → 5. questionnaire (per shoot): macOS dialogs for only unresolved fields
  → 6. scaffold + copy: create folders, copy to Photo/RAW and Video/RAW,
        sha256 verify each file, never delete from card
  → 7. manifest + ledger + notification "Offloaded 412 files → People/…/Mangos 2026"
```

### What is automated vs asked

| Field | Automated how | Asked when |
|---|---|---|
| SSD present / card present | volume UUID + `DCIM/` check | never |
| Shoot boundaries | capture-time gaps | never (shown in dialog summary) |
| Top-level category | Vision labels → taxonomy map | always shown as top-3 pick list, preselected; skipped if confidence ≥ threshold **and** not `People` |
| Personal vs Client Work | faces/humans present → `People` | only for `People` |
| Subcategory path (e.g. `Events/Education/Graduation — SSD/High School`) | drill-down lists built from **existing folders** on SSD | one `choose from list` per level, with "New folder…" option |
| Client / subject name | existing client folders offered first | text entry (cannot be inferred) |
| Descriptor (Wedding, Modeling, Mangos…) | none | text entry, optional |
| Location | GPS reverse geocode; blank if no GPS | prefilled editable text |
| Year / date | EXIF capture date | never |
| Final folder name | template `{subject} – {descriptor} – {location}` (en dash), or `{client}/{session} {year}` for repeat clients | final editable confirmation showing the full destination path |

If the operator cancels any dialog, the shoot goes to `JB Photography/_Inbox/<YYYY-MM-DD> – Unsorted/` (still hash-verified), so nothing is lost and it can be filed later with a `--refile` flag.

### Dialogs

Plain `osascript` from Python (`display dialog`, `choose from list`, `display notification`) — no extra dependency. The question set lives in the config file so it can be adjusted without code changes.

### Folder scaffold

```text
<category path>/<Shoot Name>/
├── Photo/
│   ├── RAW/        ← ARW + camera JPG + XMP
│   └── Exports/
└── Video/          (created only if the shoot has video)
    ├── RAW/        ← MP4 + XML
    └── Exports/
```

Name collisions: if the target shoot folder exists, merge into it only after the dialog confirms. Never create `(Dup)` folders. Filename collisions with different hashes are an error, not overwritten.

## Files to add / change

New code — `scripts/python/stage0/` (follows the existing `sys.path` + `scripts.python.common` import pattern from `scripts/python/stage2/01_build_checkpoint_manifest.py`; reuse `write_json` / `ensure_parent_dir` from `scripts/python/common/io_utils.py`):

- `volumes.py` — find SD card mount(s) and the SSD by UUID (`diskutil info -plist`).
- `inventory.py` — exiftool JSON inventory, ledger filtering, time-gap shoot segmentation.
- `classify.py` — preview extraction, Vision requests via `pyobjc-framework-Vision`, score aggregation, taxonomy mapping, optional reverse geocode.
- `taxonomy.py` — read the live SSD folder tree (ignoring `.lrdata`, `__LrC*`, dotfiles) to build dialog choices; build the shoot-folder name.
- `dialogs.py` — osascript wrappers + the questionnaire flow.
- `transfer.py` — scaffold, copy (`shutil.copy2`), sha256 verify, ledger append.
- `01_run_sd_offload.py` — CLI orchestrator (`--dry-run`, `--card PATH`, `--no-dialog`, `--refile`).
- `02_build_stage0_manifest.py` — compact review manifest, matching the Stage 1–5 manifest scripts.
- `config/stage0_offload.toml` — SSD volume UUID + photo root, gap hours, sample size, confidence threshold, Vision-label → taxonomy map, dialog questions.
- `requirements.txt` — `pyobjc-framework-Vision`, `pyobjc-framework-CoreLocation` (same pattern as `scripts/python/stage4/requirements.txt`).
- `launchd/com.jbphoto.sd-offload.plist` — `StartOnMount` agent calling the orchestrator with the repo `.venv` Python; installed via an `install-agent` subcommand (not auto-installed).

Outputs / state:
- `outputs/stage0/offloads/<timestamp>_<card-label>.json` — per-run manifest: card identity, per-file source path, destination, sha256, size, capture time, shoot id, classifier scores, questionnaire answers (only what was answered, no inference is presented as fact).
- `~/.jbphoto-offload/ledger.jsonl` + `agent.out/err` — idempotency ledger and logs (outside the repo, matching the `~/.pathwatch` convention).
- `data/` is untouched: offloaded RAWs go to the SSD, not into the repo.

Docs:
- `pipeline_stages/000_sd-ingest-offload/README.md` — problem, governing principles, boundary + handoff-state callouts matching the other stages.
- `README.md` — add Stage 0 to the stage list and reading paths; keep the claims modest (Vision labels are suggestions, confirmed by the operator).
- `docs/adr/0005-on-device-classification-with-operator-confirmation.md`.
- `docs/terminology.md` — add `shoot`, `offload ledger`.
- `scripts/python/README.md` — add `stage0/` (and the missing `stage5/`) to the layout.

## Tests

`tests/stage0/` (first real tests in the repo, stdlib `unittest` so no new runner is needed):
- shoot segmentation on synthetic capture times,
- taxonomy tree building against a temp directory mirroring the SSD layout,
- folder-name template (en dash, repeat-client form, special characters),
- label→taxonomy scoring with a fake Vision result,
- transfer: copy + hash verify + ledger idempotency + collision refusal, against temp dirs.
Vision and osascript are behind small interfaces so tests inject fakes.

## Verification

1. `python3 -m unittest discover tests` — all Stage 0 tests pass.
2. Dry run against a fake card: `python3 scripts/python/stage0/01_run_sd_offload.py --card /tmp/fakecard --dry-run` using a few `data/live_workspace/*.ARW` copied into `DCIM/100MSDCF/` → prints shoots, classifier top-3, planned destination; writes nothing to the SSD.
3. Classifier sanity check: run `classify.py` on `data/stage4/rendered_targets/lightroom_jpeg_exports/*.jpg` and print the top labels.
4. Real run with the SD card and SSD: walk through the dialogs, confirm files land under the chosen path with `Photo/RAW` (+ `Video/RAW`), manifest hashes match, and the card is untouched.
5. Reinsert the same card → ledger makes it a no-op (notification: "nothing new").
6. Unplug the SSD, insert the card → "Plug in Samsung SSD" notification, no copy.
7. Install the launchd agent, eject and reinsert the card → pipeline fires on its own.

## Out of scope (future)

- Auto-launching the Lightroom import with the Stage 1 ingest preset.
- Cleaning up legacy folders (`RAW/Photo` layout, `(Dup)` Nascar).
- Formatting or deleting the card after offload.
