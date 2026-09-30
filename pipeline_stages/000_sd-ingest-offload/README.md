# Stage 0 - SD Card Ingest and Offload

Stage 0 moves a shoot from the camera card onto the photo SSD before
Lightroom import. It inventories the card, splits it into shoots,
suggests a taxonomy category with on-device Apple Vision labels, asks
the operator only what cannot be inferred, then copies each file with
SHA-256 verification and records a manifest.


## Problem

Offloading used to be manual: plug in the card, create folders by hand
under `JB Photography/…`, drag files across, and hope nothing was
missed. Folder naming drifted as a result: `RAW/Photo` next to
`Photo/RAW`, en dashes next to em dashes, a `(Dup)` shoot folder, and a
`RAW (MISSING)` folder.

The problem is not copying bytes. It is making the copy verifiable and
the destination consistent, without pretending the machine knows the
client name or the intent of a shoot.


## Governing Principles

- **Never destructive at the source:** card files are only read. Stage 0
  never deletes, moves, or formats anything on the card.
- **Verify before trusting:** every file is hashed while it is copied,
  re-read at the destination, and compared before it is renamed into
  place (see [ADR 0004](../../docs/adr/0004-hash-manifested-stage-checkpoints.md)).
- **Suggest, then confirm:** Vision labels rank candidate categories.
  They are recorded as suggestions, not facts. People shoots and
  low-confidence shoots always go to the operator
  ([ADR 0005](../../docs/adr/0005-on-device-classification-with-operator-confirmation.md)).
- **Ask only what cannot be inferred:** shoot boundaries, capture year,
  and media type come from EXIF. Client name, personal vs client work,
  and descriptor come from short macOS dialogs.
- **Fail safe:** a cancelled dialog files the shoot under
  `_Inbox/<YYYY-MM-DD> – Unsorted/`, still hash-verified, to be filed
  later with `--refile`.
- **Refuse, never overwrite:** a same-name file with different content
  stops the run. Merging into an existing shoot folder requires an
  explicit confirmation. No `(Dup)` folders are created.


## Flow

```text
launchd StartOnMount (one run per mount event)
  1. detect     SD card (DCIM/ + Sony layout) and the SSD (by volume UUID)
                SSD missing -> "Plug in Samsung SSD" notification, exit
  2. inventory  exiftool -json: capture time, camera model, GPS, file type
                files already in the offload ledger are skipped
  3. segment    split into shoots at capture-time gaps (default 3 h)
                and date changes
  4. classify   sample up to 12 frames per shoot, embedded JPEG previews,
                Vision classification + face/human detection,
                label -> taxonomy map, optional reverse geocode
  5. ask        macOS dialogs for unresolved fields only
  6. copy       scaffold <Shoot>/Photo/{RAW,Exports} (+ Video/{RAW,Exports}),
                copy + SHA-256 verify, append to the ledger
  7. record     per-run manifest + "Offloaded N files -> ..." notification
```


## What Is Automated And What Is Asked

| Field | Automated how | Asked when |
|---|---|---|
| Card and SSD present | `DCIM/` layout check, SSD volume UUID | never |
| Shoot boundaries | capture-time gaps | never (shown in the dialog prompt) |
| Top-level category | Vision labels mapped through config | shown as a ranked pick list unless the top suggestion clears the threshold and is not `People` |
| Personal vs client work | none | first folder level under `People` |
| Subcategory path | folder lists read from the SSD | one pick list per level, with "New folder…" |
| Client or subject name | existing client folders offered | text entry |
| Descriptor | none | optional text entry |
| Location | GPS reverse geocode, when GPS exists | prefilled, editable |
| Year | EXIF capture date | never |
| Final destination | `Subject – Descriptor – Location` or `Client/Session Year` | editable confirmation |


## Folder Scaffold

```text
<category path>/<Shoot Name>/
├── Photo/
│   ├── RAW/        ARW + camera JPG + XMP
│   └── Exports/
└── Video/          only when the shoot has video
    ├── RAW/        MP4 + Sony clip XML
    └── Exports/
```


## Artifacts

```text
outputs/stage0/offloads/<timestamp>_<card-label>.json
  per-run manifest: card identity, per-file source, destination,
  SHA-256, size, capture time, shoot id, classifier suggestions, and
  the answers the operator gave

outputs/stage0/stage0_manifest.json
  compact index that hashes the per-run manifests

~/.jbphoto-offload/ledger.jsonl
  append-only offload ledger; a reinserted card is a no-op

~/.jbphoto-offload/agent.out, agent.err
  launchd agent logs
```

RAW files go to the SSD, not into this repository. `data/` is not
touched by Stage 0.


## Running It

```bash
pip install -r scripts/python/stage0/requirements.txt

# plan only: inventory, classify, and print destinations
python3 scripts/python/stage0/01_run_sd_offload.py --card /Volumes/Untitled --dry-run

# full run with dialogs
python3 scripts/python/stage0/01_run_sd_offload.py

# file an inbox folder later
python3 scripts/python/stage0/01_run_sd_offload.py --refile "<SSD>/JB Photography/_Inbox/2026-05-10 – Unsorted"

# install the StartOnMount agent (not installed automatically)
python3 scripts/python/stage0/01_run_sd_offload.py install-agent

# compact review manifest over all runs
python3 scripts/python/stage0/02_build_stage0_manifest.py
```

`--no-dialog` skips the questionnaire and plans every shoot for the
inbox. Settings, the Vision label map, and the dialog wording live in
`scripts/python/stage0/config/stage0_offload.toml`.

The launchd agent's Python needs macOS access to removable and external
volumes. If macOS blocks it, the run stops with an "Operation not
permitted" message that names the executable to allow under System
Settings > Privacy & Security.


## Boundary And Handoff

> **Boundary:** Stage 0 offloads and files capture data. It does not
> import into Lightroom, clean up legacy folders, or format the card.
> Vision output is a suggestion the operator confirms; no category,
> name, or location is recorded as fact unless the operator gave or
> confirmed it.
>
> **Handoff state:** Stage 1 receives each shoot as a hash-verified
> folder in the SSD taxonomy, with `Photo/RAW` (and `Video/RAW`) ready
> for Lightroom import and a manifest tying every file back to the card.
