# Future Work

This directory holds scoped extensions that build on the current
pipeline evidence but are not yet implemented as active workflow stages.

Future-work documents should preserve the distinction between:

- implemented repository behavior
- proposed measurement surfaces
- possible downstream applications
- claims that still need validation artifacts


## Proof-Of-Capability Spikes

A proof-of-capability spike is a bounded exploratory test that resolves
one implementation uncertainty and leaves behind a small inspectable
artifact.

Use this framing when the repository needs to learn whether a tool,
workflow boundary, or file format can support a proposed capability
before building a durable stage implementation.

Good spike outputs include:

- a tiny real input example
- a generated JSON report or manifest
- a pre/post checkpoint pair
- a documented finding and next decision

The point is not to ship the finished workflow. The point is to turn an
unknown capability into evidence that can be reviewed, repeated, or
discarded.

Current future-work notes:

- [Smart Conditioning For ML Compute Optimization](smart-conditioning-ml-compute-optimization.md)
- [Personal Editing Style As Conditional Policy](personal-editing-style-conditional-policy.md)
- [Lightroom Edit Recipe Execution Boundary](lightroom-edit-recipe-execution-boundary.md)
- [Crop Auto vs Upright Level Spike](crop-auto-vs-upright-level-spike.md)
- [JPEG to RAW Edit Transfer Spike](jpeg-to-raw-edit-transfer-spike.md)
