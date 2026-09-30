# Python Utilities

This directory contains stage-scoped Python helpers for extracting,
auditing, validating, and materializing workflow artifacts across the
pipeline stages.

The scripts are not intended to replace the Lightroom-centered workflow.
Their role is to make the system inspectable, reproducible, and useful
to downstream consumers by turning Lightroom-adjacent artifacts such as
XMP sidecars, manifests, review sheets, parameter exports, and serving
summaries into structured validation and handoff surfaces.

Documentation screenshots and diagrams should remain in each stage's
`assets/` tree. Machine-readable workflow artifacts should live
separately so the scripts do not have to treat README evidence images as
analysis inputs.

<br>

## Evidence Role

At the project level, the intended evidence stack is:

1. workflow/system design evidence expressed through stage prose,
   workflow images, diagrams, and operational notes
2. executable extraction, validation, and manifesting grounded in
   underlying workflow artifacts such as RAW files, XMP edit parameters,
   review sheets, and exported manifests
3. handoff and serving artifacts that expose assumptions for downstream
   operational or ML/data-science evaluation
4. tests and executable checks that keep extraction, transformation, and
   packaging paths reproducible

In other words, the visual workflow artifacts explain the observed tool
behavior, while the scripts in this directory turn that behavior into
structured validation, handoff, and serving surfaces.

<br>

## Layout

```text
data/
├── live_workspace/       # mixed RAW/XMP rolling Lightroom-sidecar state
├── stage1/
├── stage2/
│   ├── reference_state/
│   │   └── xmp_preconditioning/
│   ├── conditioned_state/
│   │   └── xmp_postconditioning/
│   └── sidecar/
└── stage3/
    └── sidecar/

scripts/python/
├── README.md
├── common/
│   ├── __init__.py
│   └── io_utils.py
├── stage0/
│   ├── __init__.py
│   ├── 01_run_sd_offload.py
│   ├── 02_build_stage0_manifest.py
│   ├── classify.py
│   ├── config.py
│   ├── dialogs.py
│   ├── inventory.py
│   ├── taxonomy.py
│   ├── transfer.py
│   ├── volumes.py
│   ├── requirements.txt
│   ├── config/
│   │   └── stage0_offload.toml
│   └── launchd/
│       └── com.jbphoto.sd-offload.plist
├── stage1/
│   ├── __init__.py
│   ├── 01_verify_stage1_xmp_source_pairs.py
│   ├── 02_extract_and_report_stage1_metadata_state.py
│   ├── 03_validate_stage1_metadata.py
│   └── 04_build_stage1_manifest.py
├── stage2/
│   ├── __init__.py
│   ├── 01_build_checkpoint_manifest.py
│   ├── 02_extract_develop_settings.py
│   ├── 03_audit_stage2_parameters.py
│   └── 04_build_stage2_manifest.py
├── stage3/
│   ├── __init__.py
│   ├── 01_extract_mask_state.py
│   ├── 02_compare_mask_state.py
│   ├── 03_create_stage3_review_sheet.py
│   ├── 04_ingest_stage3_review_results.py
│   └── 05_build_stage3_manifest.py
├── stage4/
│   ├── __init__.py
│   ├── 01_extract_pixel_signal_metrics.py
│   ├── 02_build_feature_inventory.py
│   ├── 03_build_dataset_readiness_report.py
│   ├── 04_build_ml_handoff_contract.py
│   └── 05_build_stage4_manifest.py
└── stage5/
    ├── __init__.py
    ├── 01_build_serving_exports.py
    └── 02_build_stage5_manifest.py
```

<br>

## Intent

- `common/`: shared filesystem and serialization helpers
- `stage0/`: SD-card inventory, shoot segmentation, on-device category
  suggestions, operator dialogs, hash-verified offload, and manifest
  generation
- `stage1/`: metadata extraction, validation, and manifest generation
- `stage2/`: develop-setting extraction, parameter auditing, and
  manifest generation
- `stage3/`: review-sheet creation, review-result ingestion, and
  manifest generation
- `stage4/`: RAW pixel-signal extraction, feature inventory, dataset
  readiness, ML handoff contract, and manifest generation
- `stage5/`: operational serving exports and manifest generation

These files are CLI entrypoints for producing and validating the
machine-readable evidence, handoff contracts, and serving exports that
complement the stage prose.

<br>

## Artifact Boundary

- `pipeline_stages/.../assets/images/`: screenshots and workflow-image
  evidence used in the prose
- `pipeline_stages/.../assets/diagrams/`: explanatory diagrams for
  documentation
- `data/live_workspace/`: shared mutable Lightroom workspace holding
  mixed RAW and XMP files; stages observe or checkpoint it, but no
  single stage owns it
- `outputs/stage1/`: durable Stage 1 analysis artifacts, including the
  extracted metadata report, validation report, and manifest
- `data/stage2/reference_state/xmp_preconditioning/`: frozen XMP
  checkpoint captured before Stage 2 Develop edits
- `data/stage2/conditioned_state/xmp_postconditioning/`: frozen XMP
  checkpoint captured after Stage 2 baseline conditioning
- `data/stage2/sidecar/`: optional ad hoc sidecar input location
- `data/stage3/sidecars/`: XMP sidecars or exports related to mask
  propagation state when available
- `data/stage3/review_sheets/`: human review inputs/outputs for
  Stage 3 qualification and evaluation

This keeps qualitative README evidence separate from script inputs and
allows the Python utilities to target a realistic live-workspace model.

<br>

## Validation Model

The scripts in this directory are expected to support several distinct
validation surfaces over time:

- **XMP and metadata extraction:** prove what Lightroom wrote into a
  rolling live workspace and what each extracted checkpoint captured
- **Checkpoint manifesting:** hash frozen checkpoint folders so later
  extraction and comparison artifacts can prove which sidecar snapshots
  they used
- **Edit-parameter auditing:** quantify how adjustment settings change
  across a dataset or scene group
- **Manifest generation:** produce stable external records of stage
  inputs, outputs, and review checkpoints
- **Review-sheet support:** structure human evaluation where the proof
  still depends on perceptual judgment
- **Future RAW/pixel analysis:** provide a place for stronger numerical
  analysis if the project later measures source signal, rendered-output
  behavior, or parameter dispersion directly

This means the scripts can eventually support claims at multiple levels:

- what the source image signal looked like
- what edit parameters were applied
- what the workflow state looked like before and after each stage
- what later tests can reproduce or validate automatically

<br>

## Intended Outputs

Outputs include:

- normalized metadata extracts
- stage validation reports
- stage manifests
- exception logs
- review sheets
- summary reports

Example output locations:

- `outputs/stage0/offloads/<timestamp>_<card-label>.json`
- `outputs/stage0/stage0_manifest.json`
- `outputs/stage1/extracted_stage1_metadata.json`
- `outputs/stage1/stage1_metadata_validation_report.json`
- `outputs/stage1/stage1_manifest.json`
- `outputs/stage2/checkpoints/stage2_preconditioning_checkpoint_manifest.json`
- `outputs/stage2/checkpoints/stage2_postconditioning_checkpoint_manifest.json`
- `outputs/stage2/extracts/stage2_extracted_preconditioning_develop_settings.json`
- `outputs/stage2/comparisons/stage2_develop_parameter_comparison.json`
- `outputs/stage2/stage2_manifest.json`
- `outputs/stage3/stage3_manifest.json`
- `outputs/stage3/pipeline/`
- `outputs/stage3/probes/`
- `outputs/stage4/stage4_manifest.json`
- `outputs/stage4/features/`
- `outputs/stage4/handoff/`

Stage 0 offloads a camera card (dry run first), then indexes the
per-run manifests:

```bash
python3 scripts/python/stage0/01_run_sd_offload.py --card /Volumes/Untitled --dry-run
python3 scripts/python/stage0/01_run_sd_offload.py
python3 scripts/python/stage0/02_build_stage0_manifest.py
```

Stage 2 checkpoint manifests can be regenerated with:

```bash
python3 scripts/python/stage2/01_build_checkpoint_manifest.py
```

After Lightroom Develop edits are applied and postconditioning sidecars
are copied into `data/stage2/conditioned_state/xmp_postconditioning/`,
generate the postconditioning manifest with:

```bash
python3 scripts/python/stage2/01_build_checkpoint_manifest.py \
  --checkpoint-root data/stage2/conditioned_state/xmp_postconditioning \
  --checkpoint-label stage2_postconditioning_state \
  --mutable-origin-root data/live_workspace \
  --output outputs/stage2/checkpoints/stage2_postconditioning_checkpoint_manifest.json
```

After Stage 2 checkpoint manifests, extracts, and comparison artifacts
are current, generate the compact Stage 2 review manifest with:

```bash
python3 scripts/python/stage2/04_build_stage2_manifest.py
```

After Stage 3 extracts and comparisons are current, generate the compact
Stage 3 review manifest with:

```bash
python3 scripts/python/stage3/05_build_stage3_manifest.py
```

After Stage 4 RAW metrics and handoff artifacts are current, generate
the compact Stage 4 review manifest with:

```bash
python3 scripts/python/stage4/05_build_stage4_manifest.py
```

<br>

## CLI Philosophy

Each script is structured as a focused CLI entrypoint with:

- argument parsing
- clear responsibility
- conservative defaults
- durable JSON output

<br>

## Implementation Priority

The initial version is intentionally lightweight. The first
implementation priority should likely be Stage 1, since XMP metadata
extraction and manifest validation are the clearest bridge between
Lightroom state and external analysis.

Stage 2 is the strongest next candidate because it can eventually
support both qualitative workflow claims and quantitative inspection of
develop settings, scene grouping, tonal adjustments, and downstream
parameter convergence.

The cleanest current strategy is:

1. **Stage 1:** mixed RAW+XMP live workspace first, with extracted
   metadata, validation, and manifest artifacts for auditability
2. **Stage 2:** XMP sidecars plus an optional curated RAW subset.
   Stage 2 extraction can run against any explicit XMP sidecar set, but
   durable claims should use frozen preconditioning and postconditioning
   checkpoints copied from the shared `data/live_workspace/`. The input
   model label records whether the extracted values represent an
   upstream reference state, a conditioned Stage 2 state, or another
   workflow boundary.
3. **Stage 3:** XMP sidecars plus review manifests, with optional
   rendered exports for side-by-side inspection
4. **Stage 4:** cross-stage feature inventory and ML-readiness handoff.
   Stage 4 packages evidence for future modeling review, but does not
   train or claim a model.

<br>

## Data Flow

Stage 0 runs once per card insert, upstream of Lightroom:

1. `01_run_sd_offload.py`
   detects the card and SSD, inventories and segments shoots, suggests
   categories, runs the dialogs, copies with hash verification, and
   writes a per-run manifest.
2. `02_build_stage0_manifest.py`
   indexes and hashes the per-run manifests.

Stage 1 scripts are numbered because their execution order is part of
the workflow contract:

1. `01_verify_stage1_xmp_source_pairs.py`
   confirms RAW/XMP identity before any derived evidence is trusted.
2. `02_extract_and_report_stage1_metadata_state.py`
   normalizes the verified workspace into JSON evidence.
3. `03_validate_stage1_metadata.py`
   applies Stage 1 assertion rules to the extracted JSON.
4. `04_build_stage1_manifest.py`
   packages the validated Stage 1 evidence into a manifest.

Stage 2 now follows the same numbering convention:

1. `01_build_checkpoint_manifest.py`
   hashes a frozen XMP checkpoint folder. This script is run for each
   Stage 2 checkpoint boundary, including preconditioning and
   postconditioning.
2. `02_extract_develop_settings.py`
   extracts Develop settings from a frozen XMP checkpoint.
3. `03_audit_stage2_parameters.py`
   compares preconditioning and postconditioning extracts.
4. `04_build_stage2_manifest.py`
   packages Stage 2 evidence once implemented.

Stage 3 uses numbered scripts to distinguish executable order from the
verbose JSON output order:

1. `01_extract_mask_state.py`
   extracts mask, local adjustment, and point-color state from a frozen
   sidecar checkpoint.
2. `02_compare_mask_state.py`
   compares adjacent Stage 3 checkpoint extracts.
3. `03_create_stage3_review_sheet.py`
   creates human review artifacts once Stage 3 review flow is used.
4. `04_ingest_stage3_review_results.py`
   ingests review outcomes once available.
5. `05_build_stage3_manifest.py`
   packages Stage 3 evidence once implemented.

Phase 1

- verify source/sidecar pairing
- parse XMP files
- normalize Stage 1 metadata into JSON evidence

Phase 2

- implement Stage 1 validation rules
- generate pass/fail report
- generate completeness stats

Phase 3

- create workflow manifest across stages
- add exception flags
- summarize counts

Phase 4

- add Stage 2 parameter auditing if XMP supports it
- add Stage 3 review manifest/evaluation tables

Phase 5

- add RAW-linked analysis where the source signal itself should be
  measured rather than inferred from edit parameters alone
- add optional rendered-output or pixel-level measurements where visual
  proof should be strengthened quantitatively
- connect those measurements back to stage manifests and review records

Phase 6

- tests
- sample files
- CLI usage
- polished README section showing outputs
