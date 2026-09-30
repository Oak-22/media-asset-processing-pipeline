# Shared Terminology

This glossary consolidates recurring terminology used across the
repository. The terms are organized from general workflow concepts to
stage-specific vocabulary.

## General Terms



### Issue

A recurring workflow need that creates manual effort, such as a metadata
task, visual defect, variance problem, semantic region, exception case,
or editorial decision that must be handled before the image set can move
forward.

### Uncertain Inputs

Inputs whose exact state or behavior cannot be fully predicted before
runtime. In this project, the main uncertain inputs are image variance
from changing capture conditions at source and AI-generated semantic
masks whose quality depends on image content.

### Deterministic Orchestration

A workflow design pattern that makes the order of operations, inputs,
outputs, validation points, and rollback boundaries explicit, even when
the underlying data or tool behavior is variable.

### Stage Boundary

A deliberate handoff point between workflow phases. Each stage has a
clear responsibility, expected input state, output state, and validation
role before later operations depend on it.

### Validation Checkpoint

A review point used to decide whether a transformed working set is safe
to carry forward. Validation can include metadata inspection, visual
review, before/after comparison, or mask-quality review.

### Batch-Safe Operation

An operation that can be applied across many images with predictable
enough behavior that it reduces manual work without creating excessive
cleanup. Batch-safe does not mean every image receives the same exact
runtime adjustment.

### Rollback Safety

The ability to return to a known-good prior state without discarding
valuable completed work. In this project, rollback safety is supported
by stage boundaries and non-destructive edit branches.

<br>

---

<br>

## Image Workflow Concepts

<a id="dataset"></a>
### Dataset

A complete collection of images from a single photoshoot or capture
session.

<a id="culling"></a>
### Culling

The review step where the full capture set is narrowed to images worth
carrying forward based on focus, subject relevance, aesthetic value, and
edit potential.

<a id="gallery"></a>
### Gallery

A post-cull working subset of a dataset carried forward for editing,
review, and delivery. In this repository, `gallery` refers to the
culled working image set rather than the full capture set. (dataset -> (cull) --> gallery)

<a id="scene"></a>
### Scene

A distinct composition within the dataset defined by a particular
foreground, subject, and background configuration. A single dataset
typically contains multiple scenes.

<a id="RAW"></a>
### RAW

An uncompressed or minimally processed image format that preserves the
camera sensor's original luminance and color information for flexible
downstream editing. In this workflow, RAW capture retains more
recoverable signal than JPEG, but also increases variance that must
later be normalized.

### Conditioning

A broader preparation step that makes a working set safer and more
consistent for downstream operations. Conditioning may include cleanup,
normalization, reviewed edit operations, and rollback setup.

<a id="normalization"></a>
### Normalization

A specific kind of conditioning that reduces unwanted variance across
images by bringing luminance, tone, or color into a more comparable
operating range. In this workflow, normalization preserves meaningful
scene differences rather than forcing all images into one identical
look.

<a id="virtual-copy"></a>
### Virtual Copy

A non-destructive derived edit state that preserves an independent edit
timeline while referencing the same underlying source image.

<br>

---

<br>

## Metadata And AI Concepts

### Metadata Application

The process of writing ownership, authorship, classification, or
descriptive fields onto image records. In Stage 1, identity metadata is
applied during ingest/import, while semantic enrichment is applied
later in the post-import phase. In this project, `ingest` and `import`
refer to the same Lightroom operation.

### Smart Collection

A saved Lightroom query over metadata and image attributes. In this
project, Smart Collections are treated like declarative views over image
records.

<a id="semantic-region"></a>
### Semantic Region

An image area identified by meaning rather than manual pixel
coordinates, such as a person, sky, foliage, foreground, background, or
ground.

### AI Mask Definition

A procedural instruction used by Lightroom to detect and adjust a
semantic region. When propagated to another image, the definition is
recomputed against that image instead of copying fixed pixels.

### Semantic Segmentation

An AI-driven image analysis process that divides an image into
meaningful regions or object classes. In this project, segmentation
output is useful but probabilistic, so it requires qualification and
human review.

<br>

---

<br>

### Pipeline Concepts

<a id="reference-image"></a>
#### Reference Image

A representative image selected from a comparable scene group and used
as the visual target for normalization decisions. In Operation 2,
reference images help evaluate foliage hue, skin tone, or luminance
expectations without forcing unrelated scenes into the same target look.
A reference image is scoped to the scene or normalization concern it
represents; it is not a global target for the entire dataset.

<a id="automated-tonal-color-analysis"></a>
#### Automated Tonal And Color Analysis

A normalization operation that analyzes image luminance and color
distribution, then applies coordinated adjustments to exposure,
highlights/whites, shadows/blacks, contrast, color temperature, and tint
in order to reduce unwanted visual variance prior to downstream
transformations. Tonal analysis is used to establish a dataset-wide
tonal baseline; color analysis is constrained to scene-level
comparisons so natural environmental hue differences are not flattened.

<br>

---

<br>

## Stage 0 Terms

<a id="shoot"></a>
### Shoot

A run of card files grouped by capture time during Stage 0 offload. A
new shoot starts after a configured gap between captures (default three
hours) or when the capture date changes. Each shoot is filed as one
folder on the SSD and becomes the [dataset](#dataset) that later stages
work on.

<a id="offload-ledger"></a>
### Offload Ledger

The append-only JSONL record of every file Stage 0 has offloaded, with
its destination and SHA-256 hash. The ledger lets a reinserted card be a
no-op: files already recorded are skipped instead of copied again.

<br>

---

<br>

## Stage 1 Terms

### Metadata Architecture

#### Identity Layer

The protected ownership and authorship metadata established at ingest.
This layer functions as the authoritative metadata baseline for the rest
of the workflow.

#### Domain-Specific Layer

A post-import metadata preset that writes descriptive or contextual
fields associated with a domain such as weddings, graduation, or
marketing. These presets are designed to avoid destructive overlap with
the ingest-time identity baseline, except for narrowly documented
refinement cases such as `Contact > Job Title`.

#### Semantic Layer

The revisable descriptive metadata added after import, including domain
context, captions, classifications, accessibility text, and keywords.

### Keyword Design

#### Keyword List

The concrete Lightroom keyword workspace and hierarchical keyword tree
used to store, display, and manage applied keyword relationships within
the catalog.

#### Keyword Taxonomy

The conceptual design of a keyword system, including when hierarchy is useful and when flatter queryable dimensions are better.

<br>

---

<br>

## Stage 2 Terms

### Dataset And Structural Concepts

<a id="visual-tone"></a>
#### Visual Tone

The combined luminance, contrast, and color characteristics of an image
that determine its perceived brightness, warmth/coolness, and overall
visual consistency.

### Luminance Transformation Primitives

<a id="exposure"></a>
#### Exposure

A global adjustment controlling overall image brightness by shifting the
luminance distribution uniformly across all pixels.

<a id="contrast"></a>
#### Contrast

A global adjustment controlling the separation between light and dark
regions in an image, increasing or decreasing the intensity difference
across the luminance distribution.

<a id="clipping"></a>
#### Clipping

Loss of recoverable image detail in highlights or shadows due to sensor
saturation or underexposure, where pixel values are driven to their
minimum or maximum limits and no additional tonal information can be
retrieved.

<a id="dynamic-range"></a>
#### Dynamic Range

The span between the darkest and brightest image regions that still
retain recoverable detail. In practical terms, it describes how much
shadow and highlight information can be captured or preserved before
those regions collapse into clipped blacks or blown highlights.

<br>

---

<br>

## Stage 3 Terms

<a id="canonical-image"></a>
### Canonical Image

A mask-definition source image used to define the widest useful set of
AI mask definitions before those definitions are propagated across the
broader gallery. It is not necessarily the best image artistically; it
is the image with the highest utility for exercising Lightroom's
semantic mask detection paths.

<a id="mask-definition"></a>
### Mask Definition

A procedural instruction Lightroom uses to detect and adjust a semantic
region, such as a person, sky, foliage, or background. In this
workflow, the definition is what gets copied across images; the pixel
region itself is recomputed on each target image.

<a id="aggregate-mask"></a>
### Aggregate Mask

An aggregate mask combines multiple related generated masks into a
larger review or control surface, such as all detected people, a
foreground subject group, or multiple environmental regions.

<a id="propagation"></a>
### Propagation

The batch distribution of a procedural mask definition from a source
image to target images, where each target image recomputes the semantic
region locally rather than receiving copied mask pixels.

<a id="semantic-binding"></a>
### Semantic Binding

The process by which Lightroom associates a copied mask definition with
a detected region in a target image. A binding is correct when the
generated mask attaches to the intended semantic class or subject.
