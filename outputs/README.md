## Output Artifacts

This directory contains derived JSON evidence produced by the pipeline.
The JSON files are intentionally verbose because they preserve source
paths, hashes, stage labels, summaries, and per-asset records.

Read outputs by stage, then by production order:

```text
stage0/
  stage0_manifest.json as the compact review index
  offloads/ for per-run SD-card offload manifests

stage1/
  source metadata extraction, validation, and manifest

stage2/
  stage2_manifest.json as the compact review index
  checkpoints/ for frozen Develop-state checkpoint manifests
  extracts/ for Develop-setting extracts
  comparisons/ for pre/post Develop comparison

stage3/
  stage3_manifest.json as the compact review index
  pipeline/ for the formal mask-state proof path
  probes/ for exploratory Lightroom write-behavior probes

stage4/
  stage4_manifest.json as the compact review index
  features/ for RAW signal metrics and cross-stage feature inventory
  handoff/ for dataset readiness and ML handoff contract

lightroom_sdk/
  exploratory Lightroom SDK export artifacts
```

Stage-specific ordering notes live in:

- `stage2/README.md`
- `stage3/README.md`

Treat these outputs as derived evidence. When a source checkpoint,
extractor schema, or comparison script changes, regenerate the affected
artifact and every downstream artifact that depends on it.
