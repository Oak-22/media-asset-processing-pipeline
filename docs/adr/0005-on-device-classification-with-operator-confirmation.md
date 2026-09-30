# ADR 0005: On-Device Classification With Operator Confirmation

## Status

Accepted


## Context

Stage 0 offloads camera cards into an existing SSD folder taxonomy
(`Animals`, `Automotive`, `Landscape`, `People`, and so on, with deep
client and event trees under `People`). Filing a shoot correctly needs
two kinds of information:

- facts in the files: capture time, camera model, GPS, and media type
- intent that is not in the files: client name, personal vs client work,
  the descriptor used in the folder name, and which existing client
  folder a session belongs to

Image classification can help with the first decision an operator makes
(which top-level category), but its output is probabilistic. A crowd at
a race looks like `People`; a graduation portrait also scores on
`structure`. Treating those labels as facts would reintroduce the naming
drift Stage 0 exists to remove.

Classification also runs on client images, so sending previews to a
cloud service would add a privacy and dependency cost for a single-
operator workflow.


## Decision

Stage 0 uses Apple Vision on-device, through pyobjc, to suggest
categories. The operator confirms them.

- One classification per shoot, from up to 12 evenly spaced frames.
  RAW files are read through their embedded JPEG previews, so there is
  no RAW decode.
- `VNClassifyImageRequest` label confidences are averaged across frames
  and mapped to taxonomy categories through a config file. Face and
  human detections add weighted evidence for `People`.
- Candidates are ranked. The category dialog is skipped only when the
  top candidate clears a configured share of the evidence **and** is not
  in `always_ask_categories` (default: `People`).
- Every other filing field is asked in macOS dialogs, prefilled where
  possible (GPS reverse geocode for location, existing folders for
  clients).
- The per-run manifest stores classifier output under
  `classifier_suggestions`. `answers` stores only what the operator
  entered or confirmed.


## Rationale

- **Probabilistic output needs a review boundary:** this mirrors Stage 3,
  where AI masks are qualified and reviewed before they are accepted.
- **On-device keeps client images local:** no upload, no account, no
  per-image cost, and it works offline on the machine that runs Lightroom.
- **Config over code:** the label map and dialog wording change with the
  taxonomy, so they live in TOML, not in Python.
- **Cheap to be wrong:** a wrong suggestion costs one click. A wrong
  automatic filing costs a search through the SSD later.


## Consequences

### Positive

- Most shoots need a few dialog answers instead of hand-made folders.
- Folder names follow one template and one scaffold.
- The manifest separates machine suggestions from operator decisions,
  so later readers can tell which was which.

### Negative

- Vision's label vocabulary is fixed, so some categories, such as
  `Social Media`, have no mapped labels and are only reachable through
  the full category list.
- Scores are shares of the evidence, not calibrated probabilities. The
  threshold is a tuning knob, not a guarantee.
- The feature depends on macOS, pyobjc, and TCC permissions for the
  Python executable that runs the launchd agent.


## Notes

The implementation is `scripts/python/stage0/classify.py` and
`scripts/python/stage0/dialogs.py`. The label map and threshold live in
`scripts/python/stage0/config/stage0_offload.toml`.
