# Production Workflow System Design & Implementation: Baseline Conditioning

Part of the **Media Asset Processing Pipeline** umbrella project.

<br>

## Executive Summary

Large photo sets captured across changing lighting conditions often feel
visually inconsistent even when subject matter remains similar. This
stage defines a baseline-conditioning workflow that combines local
corrective cleanup applied per frame across the working set, dataset-wide tonal normalization, and
scene-level color normalization so the final
[gallery](../../docs/terminology.md#gallery) reads as coherent
rather than ad hoc. Post-cull Virtual Copy lineage protects the working
set before conditioning, and rollbackable output branches preserve the
normalized baseline for later experimentation. Just as importantly, the
stage reduces operator-driven edit drift when the editor is repeatedly
trying to match a chosen look across many similar images. The business
value is reduced editing time, lower operator comparison burden, more
consistent outputs across a heterogeneous dataset, and safer exploration
of alternate edit directions.

Within the larger pipeline, Stage 2 wraps deterministic conditioning
around heterogeneous creative input data. The source images remain
visually variable because lighting, scene composition, camera position,
and capture settings change over time; this stage reduces that variance
without flattening legitimate scene differences.

<br>

---

<br>

## Problem

High-volume photo datasets captured over long time horizons often
contain significant lighting variance across [scenes](../../docs/terminology.md#scene). Even
when the subject matter remains similar, changing sunlight conditions
alter how the camera sensor captures both brightness and color
information.

These lighting differences change the [visual tone](../../docs/terminology.md#visual-tone) of an
image, causing otherwise related photos to feel visually inconsistent.
Without a stable baseline, later adjustments interact differently with
each image, leading to visual divergence. In addition, that technical instability
produces a second-order effect: repeated manual attempts to match a preferred
[gallery](../../docs/terminology.md#gallery)
look can introduce operator-driven drift across the dataset, especially
when rollback to an earlier edit state is weak or costly.

The systems challenge is not to remove all visual difference. It is to
create a controlled operating range where downstream edits behave more
predictably while preserving authentic scene-level variation.

<br>

---

<br>

## Solution Overview

Stage 2 operates on the protected working set created after RAW culling
and initial Virtual Copy lineage setup. Its internal conditioning work
has two main operations. First, batch-safe local corrective cleanup
applied per frame across the working set removes validated capture artifacts before normalization. In this
implementation, dust/distraction removal was the safer batch cleanup
example, while Auto Transform straightening provided a reviewed
per-image corrective example with visible pass/fail outcomes. Second,
dataset-wide tonal normalization and scene-level color normalization
reduce unwanted variance while preserving natural across-scene
differences. The normalized baseline is then handed off to
further rollbackable Virtual Copy branches for later experimentation, reducing
both technical variance and the risk of operator-driven drift.

<br>

---

<br>

## Key Constraints

- [RAW](../../docs/terminology.md#RAW) capture preserves useful signal but increases dataset variance
- large datasets make continuous cross-image comparison cognitively expensive
- normalization must preserve natural scene variation rather than erase it
- later transformations perform better when input ranges are comparable

<br>

---

<br>

## Evidence Framing

This stage uses both Workflow Image Evidence and Workflow Operational
Evidence (as hinted in the root README.md under `Evidence Model`). The workflow images show observable system state, while the
operational notes capture lived production nuances from the source
photoshoot used to develop and validate the workflow. These notes are
not presented as formal benchmarks; they explain why specific design
choices exist and where the pipeline reduced real editing friction.

Operational notes are labeled consistently so the document distinguishes
between general system design, domain background, and experience-derived
design rationale.

Each note follows the same basic structure:

- **Source context:** the relevant condition from the photoshoot or editing session
- **Observed constraint:** the specific friction, variance, or failure mode encountered
- **Design implication:** how that observation influenced the pipeline design or operation order
- **Workflow value:** why the resulting choice improved recovery, consistency, or review efficiency

<br>

---

<br>

## Stage 2 Pipeline Value - In Depth

Stage 2 creates value through a lineage-protected input boundary followed
by two conditioning operations and a rollback-safe output boundary. Each
part reduces a different class of workflow risk, and the combined effect
is larger than the sum of the individual batch effects.

<br>

### Lineage Setup Value: Protected Working State

The first Virtual Copy branch occurs immediately after RAW culling, before
Operation 1 or Operation 2. This creates a protected working state for
the culled image set so cleanup and normalization do not have to operate
directly on the original RAW selection.

This is not a third conditioning operation; it is the lineage setup that
makes the later operations safer. Operations 1 and 2 can transform the
working branch, while the original culled state remains available as the
earliest rollback point.

Although Virtual Copy branching recurs at multiple control points in
Stage 2, this view captures the underlying lineage pattern they all
rely on: preserved source state plus isolated downstream experiments.

![Stage 2 lineage setup value evidence](assets/images/001_pre-operations/001_stage2-lineage-setup-value-evidence.png)

*Figure: This view shows how Virtual Copy lineage preserves the unedited RAW state while allowing parallel experiment branches to diverge safely. Each copy represents an isolated test path rather than a destructive overwrite of the baseline. Here, divergence occurs from a post-tonal state because these branches were later used for an exploratory external blur-recovery test, which was ultimately discarded from the formal workflow.*

<br>
<br>

### Operation 1 Value: Cleaner Inputs

Operation 1 covers batch-safe, dataset-scale local corrective cleanup
applied per frame. In this case
study, the validated cleanup operations were dust/distraction removal
and Auto Transform straightening. Dust removal is the safer batch
application: if no dust is present, little or no change is applied. Auto
Transform is still useful because it evaluates each image independently,
but it requires stricter review because failed straightening must be
corrected later.

The value is not only cosmetic. Cleaner inputs reduce downstream review
noise and make later normalization easier to evaluate because the editor
is comparing global image state (image-to-image coherence) rather than
repeatedly noticing the same local defect.

<br>
<br>

### Operation 2 Value: Comparable Visual Baselines

Operation 2 establishes a dataset-wide tonal baseline and
scene-level color baselines. Tonal normalization aligns exposure and
tonal distribution across the full [dataset](../../docs/terminology.md#dataset), while color
normalization operates at the [scene](../../docs/terminology.md#scene) level so legitimate
environmental hue differences are preserved.

Without this distinction, later look adjustments can either behave
inconsistently because luminance distributions vary, or overcorrect
color by forcing naturally different scenes into one shared hue target.
The goal is therefore not a single global color match, but a stable
visual baseline that preserves real scene-level foliage and ambient
color differences.

<br>

---

<br>

## Pipeline Data Flow

The following simplified diagrams illustrate the two internal
conditioning operations and the surrounding lineage boundaries. The
conditioning operations progressively reduce variance while preserving
scene-level differences.

<br>

### Input Boundary — Baseline Protection and Rollback Control

```text
RAW Images (dataset)
      ↓
Culled Gallery (earliest rollback point)
      ↓
Post-Cull Virtual Copy Working Branch
(lineage boundary before Stage 2 conditioning)
```

The initial Virtual Copy branch is created after RAW culling to protect
the source selection before cleanup and normalization. This creates a
safe working branch for Stage 2 while preserving the original culled
[gallery](../../docs/terminology.md#gallery) state as the earliest rollback point.

---

<br>

### Operation 1 — Gallery-Scale Local Corrective Cleanup

```text
Post-Cull Virtual Copy Working Branch
      ↓
Gallery-Scale Local Cleanup Applied Per Frame
(validated dust/distraction removal + reviewed Auto Transform)
      ↓
Cleaned Baseline Inputs
```
---

<br>

### Operation 2 — Global Tonal and Scene-Level Color Normalization

```text
Cleaned Baseline Inputs
      ↓
Global Tonal Normalization
(dataset-wide tonal analysis)
      ↓
Scene-Level Color Normalization
(per-scene hue and color-balance adjustment)
      ↓
Normalized Baseline Images
(reduced luminance variance and stabilized scene-level color)
      ↓

```
---

<br>

### Output Boundary — Baseline Protection and Rollback Control

```text
Normalized Baseline Images
      ↓
Rollbackable Virtual Copy Branches Created
(handoff boundary after Stage 2 conditioning)
      ↓
Alternate Edit Direction A / B
      ↓
Compare, Keep, or Revert
```

After Stage 2 conditioning, additional Virtual Copy branches preserve
the normalized baseline while allowing additional, alternate editing paths.

<br>

---

<br>

## Domain Background: RAW Capture and Signal Variance

Digital cameras typically offer two capture formats: **JPEG** and **RAW**. JPEG images are processed in‑camera using built‑in normalization, color profiles, and compression. While this produces visually pleasing images immediately, it also locks in tonal decisions made by the camera firmware and reduces the flexibility of downstream editing.

In contrast, **RAW images preserve the camera sensor's unnormalized luminance and color distribution**. This retains the full [dynamic range](../../docs/terminology.md#dynamic-range) of the captured signal and defers tonal interpretation to the post‑processing pipeline.

RAW capture therefore increases [dataset](../../docs/terminology.md#dataset) variance but enables **controlled, user‑defined normalization during post‑processing**, which motivates the normalization operation described in this stage.

Shooting in RAW is a deliberate decision because it preserves recoverable signal that would otherwise be lost in JPEG. RAW files retain significantly more highlight and shadow information from the sensor, allowing the editor to recover details from images that might initially appear unusable (see [clipping](../../docs/terminology.md#clipping)). For example, a frame with blown highlights or deep shadows can often be salvaged by recovering clipped highlight detail or lifting shadow information. In contrast, JPEG compression discards much of this recoverable signal and locks the image into a specific tone curve and color profile, making such recovery far more limited. 

> [!IMPORTANT]
> **Governing Principle:** Don't throw away potentially usable signal prematurely.

<br>

> **Operational note:** In the source photoshoot, RAW capture was
> especially important in low-light venue conditions where heavy tree
> cover reduced available light and made detail recovery more difficult.
> In that environment, RAW preserved the best chance of recovering usable
> image quality during post-processing.

<br>

This background context explains why RAW datasets exhibit higher variance and why a normalization stage becomes necessary before consistent batch edits can be applied.

<br>

### What Normalization Means Here

In this pipeline, [normalization](../../docs/terminology.md#normalization) means reducing unwanted
visual variance across a dataset while preserving meaningful scene
differences. It does not mean forcing every image to the same exposure,
white balance, or color profile.

Instead, normalization establishes a comparable baseline operating range
for downstream edits. Each image can receive different runtime
adjustments because each image starts with different luminance, contrast,
and color conditions. The batch application is shared, but the effective
transformation is image-specific.

Color normalization is also scene-specific. A yellow-green foliage scene
should not be forced to match a deeper green scene if that hue
difference reflects real location, or environmental context.
The Operation 2 foliage examples later in this document show this
distinction. In this workflow, tonal state can be normalized across the
broader dataset, but hue and color-balance decisions are evaluated
within scene groups.

Stage 2 does not use the Stage 3 canonical-image pattern. Instead, it
uses a scene-specific reference image as a visual target for
calibration judgment. The copied adjustments are therefore mostly
static edit parameters, even when the visual judgment that selected
them is scene-specific.

This distinction matters because the goal is not visual flattening. The
goal is to make later edits behave more predictably by reducing
unwanted input variance before downstream creative decisions, semantic masking, or
manual refinement are applied.

<br>

> [!IMPORTANT]
> **Governing Principle:** Converge first, diverge later intentionally.

<br>

### Conceptual RGB Divergence Example

A useful way to explain baseline conditioning is to compare how the same
manual edit behaves against two different starting states. If one image
has been baseline conditioned and another has not, the same creative
adjustment can push their sampled color values farther apart rather than
closer together.

This can be shown with representative RGB samples, either from a global
luminance region or from a scene-specific hue region such as foliage.
Here, "starting sample" means the pixel state immediately before a later
shared creative edit is applied:

```text
Target look sample:
  RGB(92, 118, 64)

Image A - not baseline conditioned:
  starting sample:          RGB(68, 96, 50)
  after creative edit: RGB(84, 130, 56)
  result: brightness moves closer, but the sample still drifts away from the target balance

Image B - baseline conditioned first:
  starting sample:          RGB(84, 113, 61)
  after same creative edit: RGB(92, 118, 64)
  result: the same edit lands on or near the intended look with less drift
```

The exact RGB values here are illustrative rather than empirically
sampled from the embedded photos. The conceptual point is that larger
per-pixel differences from the target state create larger perceptual
differences at the image level. Baseline conditioning reduces those
starting differences before the manual edit is applied, so the same edit
is less likely to amplify visible divergence from the chosen unified
look.

> [!IMPORTANT]
> **Governing Principle:** Reduce downstream drift by reducing input variance.

<br>

---

<br>

## Detailed Problem Context

Large photo sets captured across multiple lighting environments introduce
high variance in [visual tone](../../docs/terminology.md#visual-tone). The pipeline must handle diverse
conditions and scale across the dataset without introducing inconsistency.

Example capture conditions include:

- midday direct sunlight
- shaded environments
- late-afternoon or evening lighting
- high variation in light direction and angle of incidence (backlit, front-lit, side-lit, etc.)

These conditions introduce variance in:

- exposure
- contrast
- color temperature (e.g., cool, warm)
- foliage and environmental tone (e.g., light, medium, dark)

<br>

### Naive Approach: Multiple Global Editing Passes

A naive global editing strategy (e.g., applying identical exposure
adjustments across all images) yields inconsistent results. In this
workflow context, that showed up as multiple broad visual Develop preset
layers applied across the dataset:


```text
Import preset
→ secondary editing preset
→ additional correction preset
```

These are image-adjustment presets, not the Stage 1 metadata presets
used for authorship and semantic enrichment. Stage 1 intentionally uses
non-overlapping metadata preset layers; the problem here was different:
multiple broad visual adjustment presets were stacked across the same
image set without a stable conditioned baseline.

That approach introduced several issues:

- repeated global edits across the dataset
- increased pipeline complexity
- difficulty maintaining a consistent baseline
- additional manual intervention per image

The same parameter change interacts differently with each scene, so the
pipeline effectively introduced multiple global transformation stages
while increasing the risk of inconsistent results.

This parallels software systems where broad mutation of shared state is
treated as the exception rather than the rule. Repeated global changes
to a shared baseline create hidden coupling, make downstream behavior
harder to reason about, and increase the chance of silent drift across
the working set.

That technical instability creates a second-order workflow effect: the
editor must repeatedly rematch a chosen look across related images in
order to keep the gallery coherent.

> [!IMPORTANT]
> **Governing Principle:** Broad shared-state mutation is a poor strategy; prefer bounded transformations over a stable baseline.

The workflow goals are:

- establish a consistent tonal baseline across the dataset
- establish scene-level color baselines without flattening natural hue differences
- preserve natural [scene](../../docs/terminology.md#scene) differences (e.g., time-of-day mood)
- minimize manual editing effort
- avoid repeated global transformations across the editing pipeline

Importantly, the pipeline constrains variance rather than erasing it.
The in-depth normalization logic appears later in Operation 2.

<br>

---

<br>

## Technical Design & Implementation

Within the larger stage-bounded workflow system, Stage 2 collapses
multiple global edit passes into one deterministic baseline-conditioning
sequence: dataset-scale local corrective cleanup applied per frame,
followed by dataset-wide tonal normalization then scene-level color
normalization. Virtual Copy lineage protects the working set before
conditioning (pre-stage 2) and the normalized baseline after
conditioning (post-stage 2) but it is treated as a boundary mechanism
rather than an internal conditioning operation.

<br>

### Operation 1: Dataset-Scale Local Corrective Cleanup

Operation 1 covers batch-safe, dataset-scale local corrective cleanup
applied per frame before any dataset-wide normalization is applied.
Here, `local` refers to the scope of the correction within each image,
not to a narrow subset of the dataset. In this workflow, the validated
cleanup operations were dust/distraction removal and Auto Transform
straightening.

The subsection labels below mirror the Lightroom collection naming used in the working catalog: Operation 1A/1B and Operation 2A/2B correspond
to the executable review groupings used during implementation.

<br>

### Operation 1A: Dust / Distraction Removal

The source images in this example show visible dust from either the
camera body sensor or lens, lowering image quality. The Dust Distraction
Removal feature is applied to one representative image in Lightroom's
Develop module, then synchronized across the selected images.

![Dust example 1](assets/images/002_operation-1-dataset-wide-cleanup/003_stage2-local-corrective-cleanup-dust-image1.png)

<br>
<br>

![Dust example 2](assets/images/002_operation-1-dataset-wide-cleanup/004_stage2-local-corrective-cleanup-dust-image2.png)

<br>
<br>

![Dust removal panel](assets/images/002_operation-1-dataset-wide-cleanup/005_stage2-local-corrective-cleanup-dust-panel.png)

*Figure: Representative dust/distraction cleanup setup on a source image. The local correction is defined once on a visibly affected image before being synchronized across the selected working set.*

<br>
<br>

![Dust sync settings](assets/images/002_operation-1-dataset-wide-cleanup/006_stage2-local-corrective-cleanup-dust-sync-settings.png)

*Figure: Sync settings for dust/distraction cleanup. This shows the batch handoff point where the reviewed local correction is propagated across the selected images.*

<br>
<br>

![Dust sync time](assets/images/002_operation-1-dataset-wide-cleanup/007_stage2-local-corrective-cleanup-dust-sync-time.png)

*Figure: Batch synchronization time for validated dust/distraction removal across the selected working set, showing the operational cost of dataset-scale local corrective cleanup in Stage 2.*

<br>
<br>

![Dust cleanup final result](assets/images/002_operation-1-dataset-wide-cleanup/008_stage2-local-corrective-cleanup-dust-final-result-example.png)

*Figure: Final result after synchronized dust/distraction cleanup. The evidence is most valuable here not as a dramatic stylistic change, but as proof that repeated local defects can be removed early so later normalization operates on cleaner inputs.*

<br>
<br>

Because the operation is fault-tolerant, it can be applied across the
selected dataset without review since images without visible dust are left
largely unchanged. This makes it a dataset-scale cleanup step even
though the correction itself is local to small image regions. It
therefore enables efficient batch cleanup before the later
normalization and downstream editing passes.

> [!IMPORTANT]
> **Governing Principle:** Indiscriminate batching is acceptable only
> where observed fault-tolerance is high enough that unaffected images
> remain materially unchanged.

Because this kind of correction is local within each image and repeated
across many images, it is a good candidate for early batch handling. It
reduces visible dust artifacts up front so later baseline normalization
is working from cleaner inputs rather than repeatedly compensating
around the same artifacts. This ordering is deliberate: if dust cleanup
is deferred until after normalization, the workflow risks introducing
new visible repair artifacts into an already-conditioned image, which
can reduce perceived image quality and undermine the stability that
normalization was meant to establish, thus, sequence order matters.

> [!IMPORTANT]
> **Governing Principle:** Remove validated local defects before global normalization so downstream edits operate on cleaner, more stable inputs.


<br>

### Operation 1B: Auto Transform Straightening

Auto Transform straightening is also useful in Operation 1 because it
evaluates each image independently rather than applying one fixed
rotation value across the batch. This makes it another dataset-scale,
per-frame cleanup operation rather than a single global transform. In
the recorded evidence, we tested the automated straightening pass across 5 unrelated photos. 
Results show that the function worked reliably on four and failed on one (4/5 pass); the review set marked
initial photos all as red, with 4 of 5 changing to green (successfully straightend). 

This makes Auto Transform less batch-safe than dust removal. Dust removal
is largely no-op when no visible dust is present, while a failed
straightening result leaves an issue to be corrected later manually (post-pipeline). For that
reason, Auto Transform belongs in Operation 1 as a reviewed corrective
cleanup candidate, not as indiscriminate batch application.

See also: [Crop Auto vs Upright Level Spike](../../docs/future-work/crop-auto-vs-upright-level-spike.md)
for a measured comparison of the Crop tool's `Auto` straighten against
Transform > Upright Level, and why Crop `Auto` requires GUI automation
rather than the Lightroom SDK.

![Auto Transform before review](assets/images/002_operation-1-dataset-wide-cleanup/009_stage2-local-corrective-cleanup-auto-transform-before-review.png)

*Figure: Auto Transform before review. This view shows the pre-operation comparison set selected for batch straightening prior to manual verification.*

<br>
<br>

![Auto Transform after review pass/fail](assets/images/002_operation-1-dataset-wide-cleanup/010_stage2-local-corrective-cleanup-auto-transform-after-review-pass-fail.png)

*Figure: Auto Transform after review. The manually verified result set shows successful straightening outcomes in green and the known failure case in red, making the review boundary explicit rather than implicit.*

<br>
<br>

**Outcome:**
- cleaner baseline inputs before dataset-wide normalization
- reduced need to repeatedly correct the same local defect or alignment issue later
- explicit review surface for automated straightening failures
- lower operator burden during downstream review

<br>

### Operation 2: Global Tonal and Scene-Level Color Normalization

The second operation uses automated tonal analysis to establish a
comparable tonal baseline across the dataset, then applies color normalization within
scene boundaries. This reduces unwanted visual variance while preserving
legitimate environmental hue differences between scenes.

This stage adjusts:

- [exposure](../../docs/terminology.md#exposure)
- [contrast](../../docs/terminology.md#contrast)
- highlights / whites (see [clipping](../../docs/terminology.md#clipping))
- shadows / blacks (see [clipping](../../docs/terminology.md#clipping))
- scene-level color temperature
- scene-level color tint and hue balance

This is conceptually similar to feature scaling and histogram
normalization in data pipelines. The goal is not perfect grading per
image but a reduced variance baseline for downstream processing.

This is also analogous to tabular-data normalization in that it reduces
variance before downstream processing. The difference is that the
normalization target here is perceptual image state rather than numeric
feature columns.

<br>

### Operation 2A: Global Tonal Baseline

This stage primarily reduces large tonal variance across the dataset so
that downstream corrections behave predictably. Although the automated
tonal adjustments applied here can also produce secondary color shifts,
intentional color alignment is not governed at this step. Without this
normalization operation, later adjustments interact inconsistently with
each image because their underlying exposure, tonal, and scene-level
color distributions differ.
As a result, the editor is more likely to compensate manually on a
per-image basis, which increases the chance of gallery drift when trying
to maintain a consistent look.

In practice, editors attempting to correct this manually are forced into
a continuous cycle of per-image adjustments and cross-image comparison.
They must repeatedly zoom into individual images to fine-tune exposure,
tonal values, and color balance, then zoom out to evaluate consistency
across the broader dataset. This constant context switching introduces
cognitive fatigue and increases the likelihood of drift from both
scene-level and gallery-level consistency. **Once a poor sequence of
adjustments has been applied across multiple images, weak rollbackability makes recovery even harder.**

> **Operational note:** This became especially visible in group formals.
> Although those images were already highly similar, repeated manual
> rematching still introduced edit-direction drift once the workflow
> lacked a stable shared baseline.

By establishing a consistent dataset-wide tonal baseline upfront, the
pipeline removes much of this instability. By constraining color
normalization to scene groups, it also reduces repeated temperature,
tint, and hue rematching across similar images without flattening
legitimate across-scene differences. Subsequent adjustments operate on
comparable visual distributions, enabling downstream look corrections to
produce stable, repeatable results without continuous manual
recalibration.

<br>

### Operation 2B: Scene-Level Color Baseline

Foliage is a useful Operation 2 example because it exposes the
difference between legitimate scene variance and unwanted within-scene
drift. A true global hue target would be too aggressive: yellow-green
foliage in one scene should not be forced to match deeper green foliage
from a different lighting environment, as explained below.

![Foliage hue comparison](assets/images/001_pre-operations/002_stage2-intra-scene-hue-normalization-not-global.png)

*Figure: Foliage hue should be normalized within comparable scene groups, not across the full dataset. Across the three example scenes, the wedding-dress foliage scene is the strongest candidate for scene-level color calibration (Images 1-4), the group formal portraits are a weaker but still plausible candidate (Images 8-9), and the yellow-hue foliage scene (Images 5-7) is the weakest candidate because its color is already internally consistent and appears scene-authentic rather than erroneous.*

<br>
<br>


![Scene-scoped cross-image color normalization](assets/diagrams/scene-scoped-cross-image-color-normalization-v3.jpg)

*Figure: Scene-scoped cross-image color normalization proceeds in two steps. First, automated tonal normalization reduces frame-level exposure variance across comparable images, while also allowing subtle, secondary chromatic shifts. Second, scene-level reference-image color calibration aligns within-scene hue drift, such as inconsistent green cast, without forcing unrelated scenes toward one global color target.*

<br>
<br>

```text
Without scene boundaries:
  repeated manual compensation
  → cross-scene hue flattening
  → edit-state drift and weak reversibility

With scene-level foliage normalization:
  comparable scene group selected
  → hue drift reduced within the scene
  → natural across-scene foliage variance preserved
```

<br>

**Outcome:**
- reduced luminance variance across the dataset
- reduced hue/color variance within scene groups
- predictable downstream transformations
- significant reduction in repeated per-image exposure and scene-level color correction (residual adjustments may still be required in edge cases)

<br>

### Baseline Handoff: Virtual Copies and Rollback Control

Virtual Copies enter the workflow before Operation 1: after RAW culling,
the selected images are branched into an initial working state so cleanup
and normalization do not overwrite the original culled selection. After
Operation 2 establishes a stable luminance and scene-color baseline,
additional Virtual Copy branches protect that baseline from
operator-induced drift as the dataset progresses to the next stage (Stage 3: AI Semantic Mask Definition Propagation) and beyond.

Virtual Copies provide a lightweight lineage mechanism for alternate edit
paths: instead of overwriting a single edit history, the workflow can
branch an image into parallel adjustment timelines while keeping the same
underlying source asset.

In this workflow, that matters because a bad sequence of global or
domain-level adjustments can otherwise propagate across many similar
images before the editor realizes the gallery has drifted away from the
intended look.

> **Operational note:** Rollback was technically available in the prior
> workflow, but it was still costly because reverting often meant
> returning to raw source state rather than to a reusable intermediate
> baseline shared across similar group portraits. In other words,
> recovery existed, but the rollback target was too primitive to
> preserve the normalization work that should have remained stable.

**Outcome:**

- **Rollbackable experimentation:** Alternate edit directions can be
  tested without destroying the normalized baseline.
- **Comparative review:** Competing edit directions can be compared
  without forcing every experiment into one mutable history.
- **Source protection:** The first post-cull Virtual Copy keeps the
  original culled RAW selection available before cleanup and
  normalization.
- **Baseline preservation:** Once a chosen direction begins to drift,
  the editor can revert to a known-good state instead of manually
  untangling accumulated edits.

> [!IMPORTANT]
> **Governing Principle:** Preserve the normalized baseline through
> lightweight branch management over a shared source record.

<br>

---

<br>

## System Constraints & Scale Considerations

The current implementation is designed as a **local, editor-in-the-loop batch pipeline** operating within Lightroom Desktop / Classic rather than as a cloud-native or distributed image-processing system. RAW files, virtual copies, and downstream edits are managed within a local catalog-centered workflow optimized for a single operator performing interactive review and refinement.

This design favors **editing throughput, controllability, and local responsiveness**. Operations 1 and 2 are the conditioning operations that establish a normalized baseline, while the output boundary preserves that baseline during experimentation and revision.

In practical terms, the pipeline is intended to scale across **hundreds of RAW images per dataset**. The relevant engineering question is therefore not formal algorithmic complexity in the abstract, but rather **observed operational latency, throughput, and reduction in manual intervention** as dataset size increases.

<br>

### Vendor-Controlled Automation Limits Transparency

The workflow benefits from Lightroom's built-in automation, but some
stages depend on vendor-controlled black-box heuristics. This improves
usability and speed while limiting transparency into the exact internal
logic of automated tonal analysis.

<br>

---

<br>

## Failure Modes & Edge Cases

Although the pipeline reduces variance and improves editing consistency, each stage still has failure modes that require manual judgment or override.

<br>

### Operation 1 Failure Modes

The primary Operation 1 failure surface is Auto Transform rather than
dust cleanup. In this workflow, dust/distraction removal is effectively
fault-tolerant: when no relevant dust artifact is present, the synced
correction usually leaves the image materially unchanged.

Auto Transform straightening is highly effective, but it can still fail
when Lightroom's geometry inference chooses the wrong horizon or
alignment target. In the recorded review set, the automated
straightening pass succeeded on 4 of 5 sample images and failed on 1 (highlighted red),
which was sufficient to justify keeping manual review as an explicit
boundary. When that happens, the result must be flagged and corrected
manually rather than accepted as a fully reliable batch-safe outcome.

See the Auto Transform review evidence in the Operation 1 section
above, especially the post-review pass/fail figure showing the known
failure case in red and successful outcomes in green.

<br>

### Operation 2 Failure Modes and Edge Cases

Global tonal normalization and scene-level color normalization can
still produce imperfect results when scenes contain **extreme [dynamic
range](../../docs/terminology.md#dynamic-range)**, strong backlighting,
heavy [clipping](../../docs/terminology.md#clipping), mixed color
temperatures, or incorrectly grouped scene comparisons. In these cases,
automated tonal analysis may reduce variance without fully establishing a
sufficient baseline, and residual manual per-image exposure or
scene-level color correction may still be required.

An important edge case is the deliberately stylized image whose low-key
or high-contrast treatment is intentional rather than erroneous. For
example, a deliberately composed **silhouette image** — such as a
wedding couple rendered primarily as shadow shapes with little or no
recoverable facial or subject detail — may be interpreted by
Lightroom’s automated tonal analysis as unintentionally underexposed and
therefore excessively brightened — degrading image quality — even when the silhouette treatment was the
intended creative choice.

<br>

![Auto tonal analysis failure for intentional creative treatment](assets/images/004_failure-modes/001_stage2-auto-tonal-analysis-creative-intent-failure.png)

*Figure: Failure mode for automated tonal analysis under intentional creative treatment. The left image preserves the intended low-key result, while the right image shows quality degradation after the automation interprets the scene as unintentionally underexposed and brightens it too aggressively. Inspect the wedding attire of both the bride and groom for visible, undesirable pixelation.*


<br>

### Baseline Handoff Failure Modes

Virtual-copy branching can still fail when branch discipline is weak. If
the initial post-cull branch, normalized baseline branch, and later
experimental branches are not clearly named, compared, or pruned, the
editor can lose track of which branch represents the intended baseline
versus an experimental detour. In that case, branching reduces recovery
cost in theory but not in practice.


<br>

### System-Level Failure Modes

At the system level, failure can also occur when too many manual
overrides are required. Excessive exception handling reduces the
throughput benefit of the pipeline and can reintroduce the same
cross-image comparison burden that the workflow is intended to remove.
In practice, weak Operation 1 cleanup, a weak Operation 2 baseline, or
weak rollback discipline at the output boundary can each
increase downstream instability and reduce overall consistency.

<br>

---

<br>

## Observability & Validation

This implementation is validated through a layered evidence model with
two complementary proof surfaces. First, **embedded visual evidence**
and **editor-observed workflow effects (Operational Notes)** establish
the workflow intuition: they show what the conditioning stages are doing
and why the resulting image behavior is operationally useful. Second,
**RAW/XMP-linked analysis**, rendered outputs, manifests, and runnable
script/test support
provide the structured validation layer that can formalize those claims
quantitatively.

These layers are not substitutes for one another. The workflow and
visual artifacts establish the qualitative behavior first; the
RAW-to-XMP-to-rendered-output validation layer is what turns that
behavior into a
more mathematical proof surface. Because perceptual coherence, hue
alignment, and cleanup-artifact detection still matter at the rendered
image level, visual review remains a required complement even with the
RAW-to-XMP-to-rendered-output validation support.

<br>

### Qualitative Validation Surface

The qualitative validation surface is carried by the workflow images,
diagrams, before/after examples, and Operational Notes embedded
throughout this stage. These artifacts establish the workflow intuition
first: they show how the conditioning steps behave, where the review
boundaries sit, and why the resulting baseline is operationally useful
alongside the quantitative validation layer.

This matters because the final workflow claim is partly perceptual. The
editor ultimately needs to confirm image coherence, hue alignment, and
artifact-free cleanup in the rendered outputs, not only in extracted
metadata or adjustment values.

<br>

### Quantitative Validation Surface

The quantitative validation surface for this stage is the
RAW-to-XMP-to-rendered-output chain: RAW source signal, XMP edit
parameters, and the rendered outputs generated from them. This makes it possible to
distinguish between:

- source-signal variance in the captured RAW images
- edit-parameter convergence or dispersion after normalization
- rendered-output behavior after the RAW signal and XMP transforms are combined

Useful workflow metrics may still include:

- total editing time per dataset
- editing time per delivered image
- number of residual local defect or straightening corrections after Operation 1
- number of residual manual exposure or scene-level color corrections after Operation 2
- number of virtual-copy branches or reversions required when alternate
  edit directions fail after the baseline handoff

Together, these measurements would help quantify whether the pipeline
reduces manual intervention and improves throughput in practice, while
the RAW-to-XMP-to-rendered-output analysis chain provides the stronger
mathematical validation layer for the normalization claims themselves.

<br>

### Operation 1 Validation

Operation 1 is validated primarily through visual and
workflow-observable evidence. The relevant proof surface is the
dust/distraction cleanup and Auto Transform review evidence already
embedded in the section above. For dust cleanup, the central question is
whether repeated local defects are removed without introducing visible
repair artifacts or unnecessary changes to unaffected images. For Auto
Transform, the central question is whether the automated straightening
pass is useful enough at dataset scale to justify batch application
under explicit manual review rather than as a fully trusted automatic
transform.

The Auto Transform before/after review set provides the clearest
validation surface here: successful outcomes are visually confirmed, the
known failure case is explicitly marked, and the manual review boundary
is made observable rather than assumed.

Quantitative support for Operation 1 can still exist, but it is weaker
and less central than for Operation 2. Useful numerical support here is
mostly workflow-facing: synchronization time, reviewed pass/fail
outcomes, residual manual corrections, and exception counts. The
strongest proof for Operation 1 remains the visible result quality and
the clarity of the review boundary.

<br>

### Operation 2 Validation

A lightweight validation approach is to show representative before/after
image subsets from the same [dataset](../../docs/terminology.md#dataset) and visually inspect
whether automated tonal analysis reduces dataset-wide luminance variance
and whether scene-level color normalization reduces unwanted hue drift
within comparable scene groups. Operation 2 is validated through the
same visual/workflow surface as Operation 1, but with stronger
quantitative co-support. Visual comparison remains the primary artifact
for showing the perceptual behavior of this stage. In parallel, the
Stage 2 scripting layer is intended to record relevant pre- and
post-normalization adjustment values — such as
[exposure](../../docs/terminology.md#exposure), [contrast](../../docs/terminology.md#contrast), highlights / whites, shadows / blacks, color
temperature, tint, and hue-related changes — so observable image
results can be paired with structured validation and reproducibility
data. In the intended evidence model, the visual artifact establishes
the intuition while the RAW-to-XMP-to-rendered-output analysis chain
provides the stronger mathematical proof surface.

<br>

### Baseline Handoff Validation

The baseline handoff can be validated by testing alternate edit directions on
Virtual Copies and recording whether the editor can return to a known
good baseline without manual untangling. The central engineering
question is whether branching and rollback materially reduce edit-state
drift during look-matching.

Validation here is primarily visual and workflow-observable: can the
editor compare alternate directions, revert to the known-good baseline,
and preserve gallery consistency without manually untangling
accumulated edits?

<br>

---

<br>

## Design Tradeoffs

The pipeline improves consistency and throughput, but it does so through
explicit tradeoffs rather than through full automation. The tradeoffs
below are ordered to follow the same step-wise progression as Stage 2
itself.

<br>

### Upfront Cleanup and Normalization vs Downstream Speed

Operations 1 and 2 introduce upfront cleanup and normalization work, but
that cost is repaid through faster downstream editing. This is a
deliberate trade of early processing overhead for reduced repeated work
later in the pipeline.

In real editing workflows, the cost of skipping this baseline work is
not limited to cumulative time alone. When global cleanup and
normalization are not established early, the editor must repeatedly
re-correct near-identical images and re-compare them against the rest of
the gallery. That raises both cognitive load and the chance of
inconsistent edits.

<br>

### Consistency vs Authentic Scene Variation

The system is designed to reduce unwanted variance, not to eliminate all
variance. Over-normalization would flatten meaningful differences
between [scenes](../../docs/terminology.md#scene), especially when
time-of-day lighting or environmental color legitimately changes the
mood of an image.

<br>

### Controlled Manual Overrides, Not Unlimited Manual Optionality

Manual per-image overrides remain available for edge cases but are
intentionally limited. Excessive local correction increases cognitive
load, reducing editing speed, and directly diminishes the purpose of the
pipeline.

Design rationale for Controlled, not Unlimited:

- overly granular control increases cognitive load
- editing speed decreases with too many one-off overrides
- most images need minimal manual intervention after the baseline is established

> [!IMPORTANT]
> **Governing Principle:** Prioritize addressable control rather than complete control.

<br>

### Baseline Preservation and Rollback Safety vs Branch-Management Overhead

Virtual Copies preserve both the initial culled RAW state and later
known-good normalized baselines while allowing derived edit paths to
evolve independently. This trades a small amount of branch-management
overhead for safer experimentation and rollback later.

This mirrors engineering patterns such as immutable baselines,
branchable derived states, and rollbackable experimentation.

The rollback boundary gains safety by making alternate directions
recoverable, but that also introduces the need for disciplined branch
naming, comparison, and pruning. Too many unmanaged branches can create
their own form of operator confusion.

<br>

### Automation vs Editorial Control

Operations 1 and 2 automate high-frequency repetitive operations, while
the baseline handoff remains intentionally editor-guided because branch
selection, comparison, and rollback still depend on editorial judgment.

This tradeoff is especially important when the editor is comparing
multiple plausible looks. A purely linear history makes it harder to
test alternatives safely; a branchable workflow preserves control
without forcing every experiment to overwrite the baseline.

---

<br>

## Resulting Benefits of Stage 2

- consistent tonal baseline across heterogeneous input distributions
- scene-level color baselines that preserve natural hue differences
- reduced global editing passes
- safer experimentation through rollbackable edit branches
- reduced manual correction
- predictable editing pipeline mechanics

<br>

---

<br>

## Engineering Concepts Demonstrated

- deterministic sequencing of heterogeneous transformations
- dataset-scale conditioning with per-frame execution
- separation of local corrective cleanup from global baseline normalization
- scene-scoped normalization rather than indiscriminate global color matching
- lineage-preserving non-destructive branching
- rollback to known-good intermediate state rather than raw-source reset
- bounded automation with explicit human review checkpoints
- batch throughput optimization under tooling constraints
- controlled manual overrides for edge cases
- cognitive-load reduction through staged workflow design

<br>

---

<br>

## Takeaway

This photography workflow becomes a stage-boundary design problem. By
separating local cleanup, dataset-wide tonal normalization, scene-level
color normalization, and rollbackable experimentation boundaries, the
system achieves dataset consistency and editing efficiency without
sacrificing image fidelity, natural scene variance, or processing
flexibility.
