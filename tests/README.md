# Tests

This directory is reserved for executable validation support around the
workflow-observability scripts, handoff artifacts, serving exports, and
any later quantitative analysis tooling.

The tests in this repository are not meant to replace the workflow’s
visual or operational evidence. Their role is narrower and more
concrete:

- verify extraction logic over XMP sidecars, manifests, and review data
- protect schema assumptions and parsing behavior
- validate script-level transformations and reports
- validate handoff and serving-export assumptions
- support later quantitative checks over RAW-linked metadata, edit
  parameters, or rendered-output measurements when those analyses are
  implemented

In the project’s broader evidence model, tests protect the structured
proof layer: extraction logic, schema assumptions, manifests, handoff
contracts, and serving outputs remain reproducible as the system grows.

Current contents:

- `stage0/`: stdlib `unittest` coverage for Stage 0 shoot segmentation,
  taxonomy reading, folder naming, label-to-category scoring with a fake
  Vision analyzer, the dialog questionnaire with a scripted backend, and
  copy, hash verification, ledger, and collision handling in temporary
  directories

Run all tests from the repository root:

```bash
python3 -m unittest discover tests
```

Likely future contents include:

- fixture XMP sidecars
- sample manifests and review sheets
- parser and schema regression tests
- Stage 1 metadata validation tests
- Stage 2 parameter-audit tests
- Stage 3 review-ingestion tests
