# Batchability Cost Model

<br>

## Core Question

For each repeated issue, what is the cost of handling it manually per
image versus converting it to a batchable process?

This document poses that question as the cost model for assessing
pipeline value.

Here, **issue** follows the shared terminology definition: a recurring
workflow need that creates manual effort. See [Issue](terminology.md#issue).

The estimates here are benchmarked, with larger effects extrapolated. They model
how the cost shape changes when a correction operation moves from repeated
manual execution to setup, qualification where needed, batch
application, validation, and targeted exception handling.

<br>

## Issue/Correction Model

A single deliverable image can contain many issues or correction requirements
that must be addressed before final review. Some are mandatory only when
a specific condition is present, such as dust, tilted framing, weak
luminance, foliage hue drift, or a semantic region (i.e., sky) that needs local
correction.

The pipeline value comes from separating issue categories by the
automation potential of the correction operation used to address them: which
operations can be batch-applied immediately, which require
qualification first, and which must remain manual even when the same
issue appears many times.

Representative issue and correction categories include:

- **Local defects:** dust/distraction removal, with image-specific Spot Removal kept manual when the target changes per frame
- **Geometry:** straightening and crop decisions
- **Recovery:** AI-assisted recovery for borderline focus/noise cases when the image is otherwise worth keeping
- **Global visual baseline:** luminance and tonal adjustment
- **Scene-level visual baseline:** hue and color normalization within comparable scenes
- **Semantic local edits:** people, foliage, sky, background, foreground, or ground masks
- **Final artistic review:** manual refinement, crop finalization, and subjective delivery choices

<br>

## Batchability Matrix

Not every repeated issue can be addressed through batch application. Some
issues recur across a dataset but still require manual image-by-image
judgment because the target region, edit boundary, source pixels, or
aesthetic decision changes with each frame.

The useful distinction is not whether a correction is simply automated or manual, but where it falls on a continuous batchability spectrum.

| Issue / correction need | Pipeline handling | Review burden | Pipeline stage |
|---|---|---|---|
| Identity metadata | Batch-applied through ingest preset | Low | Stage 1 |
| Semantic metadata enrichment | Batch-applied through post-import presets | Low to moderate | Stage 1 |
| Dust/distraction cleanup | Batch-applied after validation | Low to moderate | Stage 2 |
| Tonal normalization | Batch-applied across dataset | Moderate | Stage 2 |
| Scene-level color normalization | Batch-applied within comparable scene groups | Moderate | Stage 2 |
| AI masks for common semantic regions | Qualified, then batch-propagated | Moderate to high | Stage 3 |
| Uncertain semantic regions | Qualified on representative examples before promotion | High | Stage 3 |
| Failed straightening, masking, or normalization cases | Exception handling | High | Stage 2 / Stage 3 |
| Image-specific Spot Removal, blemish, or skin cleanup | Manual per-image correction | High | Manual review |
| Final crop and artistic emphasis | Manual editorial decision | High | Final review |

For example, sensor dust is a strong batch candidate because the defect
can be small, repeated, and safe to remove or omit with limited visual
risk. A large blemish on a primary subject, such as a pimple that
appears across many images, is different. It may be repeated, but the
face position, expression, lighting, skin texture, and healing source
change per frame, so the correction must remain manual. In this tested
workflow, Lightroom did not dynamically remove that recognized entity (skin pimple)
across images with reliable results using either Stage 2 conditioning
techniques or Stage 3 mask propagation techniques.

Once a Stage 3 mask definition has been qualified, propagation across
the [gallery](./terminology.md#gallery) is a batch application in the
same economic sense as Stage 2
cleanup or normalization: the operation is applied at multi-image scale,
then reviewed. The difference is that probabilistic semantic detection
can create a higher exception-review burden because generated masks may
succeed, omit unavailable regions, bind to the wrong region, or produce
boundaries that need manual refinement. Stage 2 automated tonal analysis
can still fail, but its main uncertainty is image-level luminance or
color interpretation; Stage 3 adds semantic-region detection, class
binding, and mask-boundary quality as additional review surfaces.

<br>

## Stage-Level Value

### Stage 1: Metadata Foundation and Query

Stage 1 shifts metadata work from repeated manual record maintenance to
structured preset application, post-import enrichment, and reusable
query views. The savings come from reducing field-level rework,
avoiding metadata collisions, and making later retrieval faster through
filters and Smart Collections.

The main value is not only faster metadata entry. It is a cleaner state
layer: images become identifiable, queryable, and easier to segment into
working sets before visual editing begins.

### Stage 2: Baseline Conditioning

Stage 2 focuses on correction operations that establish a reliable visual baseline
before creative edits: local cleanup, tonal normalization,
scene-level color normalization, and rollback-safe branching.

The savings come from reducing repeated comparison loops. Instead of
manually trying to match brightness, tone, and color across many images
late in the edit, the workflow establishes a comparable baseline early
and protects it with Virtual Copy branches.

### Stage 3: AI Semantic Mask Definition Propagation

Stage 3 focuses on semantic operations whose behavior depends on
probabilistic AI segmentation. The savings come from defining reusable
mask logic once, propagating it across the
[gallery](./terminology.md#gallery), and reviewing
generated results instead of manually brushing each semantic region on
each image.

<br>

## Back-of-Envelope Savings Model

The pipeline changes the cost model from repeated per-image execution to
stage setup, qualification where needed, batch application, validation,
and targeted exception handling.

| Workflow area | Manual cost shape | Pipeline-assisted cost shape | Savings driver |
|---|---|---|---|
| Metadata application | Repeated field entry, ad-hoc classification, manual searching | Ingest-time identity preset, post-import semantic enrichment, reusable queries | Fewer field collisions and faster retrieval |
| Baseline conditioning | Repeated cleanup, matching, comparison, and rollback recovery per image | Batch-safe cleanup, dataset/scene-level normalization, protected correction branches | Less comparison burden and safer experimentation |
| AI mask propagation | Manual semantic masking per region per image | Canonical mask definition, batch propagation, human review | Less repetitive masking before review |

<br>

## Directional Formula

For each recurring issue and proposed correction operation, the savings can be
approximated as:

```text
manual_cost = image_count x issue_frequency x average_manual_time_correcting

pipeline_cost =
  setup_time
  + qualification_time
  + batch_execution_time
  + review_time
  + exception_fix_time

estimated_savings = manual_cost - pipeline_cost
```

The pipeline is most valuable when an issue has high frequency,
high manual repetition, and predictable enough behavior to support batch
application after any required qualification. It is less valuable when
the issue is rare, highly subjective, or cheaper to fix manually than to
qualify.

<br>

## Evidence Basis

The three sections that follow build outward from the strongest evidence to
the weakest. Their figures fall into three classes:

| Class | Meaning | Covers |
|---|---|---|
| **Measured** | Observed directly during a controlled run | Stage 3 batch runtime on a 64-image gallery |
| **Retrospective** | Attributed after the fact from a completed job | The 30-hour workflow and its internal slices |
| **Projected** | A measured rate carried onto a retrospective slice | Both extrapolation sections |

One caveat covers all of it. Only the Stage 3 batch runtime was measured.
Every hour-level figure describing the real workflow is an after-the-fact
attribution, and every reduction applied to those hours is a projection.
The sections below label which is which and leave the warning here.

<br>

## Stage 3 Measured Experiment

Stage 3 is the one stage with a controlled comparison: a bounded manual
workload set against an observed batch runtime on the same gallery slice.
See [Stage 3 evidence](../pipeline_stages/003_ai-semantic-mask-definition-propagation/README.md#back-of-the-envelope-time-savings).

```text
gallery size:                            64 images
qualified masks per image:               9
theoretical maximum mask applications:   64 x 9 = 576

manual baseline (modeled at ~10 s per mask application):
  576 x 10 s = 5,760 s = 96 minutes

batch runtime (observed in Lightroom):
  7 minutes = 420 s

reduction:
  96 - 7 = 89 minutes
  = ~93% less operator time
```

Two details define what the number covers. The batch runtime was observed
directly, while the manual baseline is modeled from a ~10-second-per-mask
rate. And the scope is mask application: qualification setup, exception
handling, and downstream refinement of generated masks sit outside it, and
the [Batchability Matrix](#batchability-matrix) rates that review burden as
moderate to high.

This ~93% is the measured result the rest of the model builds on.

<br>

## Projecting Stage 3 onto a Real Workflow

The measured rate becomes useful when carried onto a job of real size.

An eight-hour wedding event produced approximately 1,500 RAW images, of
which 350 were culled, edited, and delivered across 30 hours of wall-clock
work with no pipeline automation in place. Retrospectively, manual masking
and refinement account for about 20 of those hours.

```text
masking and refinement slice:         20 hours
rest of the workflow (30 - 20):       10 hours

slice after the ~93% Stage 3 rate:    ~1.4 hours
projected total (10 + 1.4):           ~11–12 hours
```

Two assumptions carry that projection. The 20-hour slice bundles masking
with refinement while the measured rate covers masking alone, so the
further that slice leans toward refinement, the more the projection
overshoots. And the remaining 10 hours are held flat, including the Stage 2
normalization work this projection leaves untouched.

<br>

## Extending to Stage 2

Stage 2 has no timing experiment behind it, but it has the same cost shape
as Stage 3 and a retrospective slice of the same job to work against.

Of the 30 hours, about 6–7 are attributed to scene-level hue and color
normalization across the delivered image set. The mechanism that would
compress them is the one the [Batchability Matrix](#batchability-matrix)
already describes: define a correction once against a reference image,
batch-apply it within a comparable scene group, review the result. That is
the same economics as mask propagation, applied to a slice carrying less
semantic uncertainty — tonal and color interpretation rather than region
detection, class binding, and boundary quality.

The association is strong enough to project against, and loose enough that
the recovery rate is better left as a dial than borrowed from Stage 3:

| Stage 2 recovery assumed | Stage 2 slice | Projected 30-hour total |
|---|---|---|
| None — Stage 3 only | 6–7 h | ~11–12 h |
| Half | ~3–3.5 h | ~8 h |
| Stage 3's measured ~93% | ~0.5 h | ~5–6 h |

The middle row is the defensible one. It assumes Stage 2 automation
recovers half of a slice whose correction operation is already
batch-applied elsewhere in the pipeline, and it lands the 30-hour job near
8 hours.

Together the two stages address 26–27 of the original 30 hours. That
combined figure describes the addressable surface — the share of the job
running through batchable correction operations — leaving roughly 3–4 hours
of ingest, culling, final review, and export outside it.

<br>

## Summary

Batchability changes where the editor spends attention: less repeated
mechanical editing, more setup, qualification, validation, exception
handling, and final creative review.

Across the three stages, the accumulated value comes from stacking these
stage-local cost-shape changes. Metadata becomes easier to retrieve,
baseline conditioning reduces visual comparison work, and semantic mask
propagation reduces repeated local editing effort. The safest way to
present that cumulative value is to first show each stage's savings on
its own terms, then describe the combined workflow effect second.

The figures above follow that order deliberately: a measured Stage 3
result, carried onto a real 30-hour job, then extended to Stage 2 on the
strength of a shared cost shape. Each step rests on weaker evidence than
the one before it, and each is labeled where it appears.

Future work may extend this cost model from operator-time savings into
compute-shape optimization for downstream ML workflows. See
[Smart Conditioning For ML Compute Optimization](future-work/smart-conditioning-ml-compute-optimization.md).
