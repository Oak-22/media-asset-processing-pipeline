# Crop Auto vs Upright Level Spike

## Purpose

This spike tests whether Stage 2 Operation 1B straightening can run as a
background batch without driving Lightroom's GUI.

The preferred straightening result comes from the Crop tool's `Auto`
button. The question is whether a scriptable surface can reproduce that
result:

```text
Crop tool Auto button (preferred result, GUI only)
  vs
Transform > Upright Level (scriptable through the Lightroom SDK)
```


## Control Surfaces Checked

| Surface | Result |
|---|---|
| Lightroom SDK (`LrDevelopController`, `photo:applyDevelopSettings`) | Cannot invoke Crop `Auto`. Can set a fixed `CropAngle` / `straightenAngle`, or enable Upright Level (`PerspectiveUpright = 3`). |
| MIDI2LR and controller plug-ins | Built on the same SDK; expose Upright modes, not Crop `Auto`. |
| Menu commands and keyboard shortcuts | No menu item or default shortcut triggers Crop `Auto` (Lightroom Classic 15.1 menu tree inspected). |
| Auto Sync across a selection | Copies one computed angle to every photo; does not recompute per photo. |
| Mouse events posted to the Lightroom process | Keystrokes are accepted in the background; clicks are rejected, including events carrying the target window ID. |
| GUI automation with the real cursor | Works. Implemented as [`run_crop_auto_straighten.sh`](../../scripts/macos/stage2/run_crop_auto_straighten.sh). Lightroom must stay frontmost. |

A catalog read also showed that a Crop `Auto` click writes Upright
analysis state (`UprightVersion`, `UprightTransformCount = 6`) even with
Transform off. The two controls share Lightroom's Upright analysis, which
made Upright Level the one plausible scriptable substitute.


## Method

Two Virtual Copy branches of the same 20 originals from one event shoot
were compared:

```text
Upright Level branch (Copy 3)
  -> plug-in applies Upright Level, reads UprightTransform_3,
     converts it to a rotation, restores the prior Upright mode
  -> lightroom_sdk_upright_level_probe.json

Crop Auto branch (Copy 2)
  -> run_crop_auto_straighten.sh applies Crop > Auto per photo
  -> plug-in records CropAngle
  -> lightroom_sdk_crop_auto_angle_record.json

compare_crop_auto_vs_upright_level.py
  -> lightroom_sdk_crop_auto_vs_upright_level_comparison.json
```

`UprightTransform_3` is a row-major 3x3 similarity in normalized image
coordinates, so its rotation is `atan2(sqrt(|b*c|), a)` with the sign of
`c`. Crop Angle uses the opposite sign convention.


## Results

Upright Level returned a rotation for 18 of 20 photos. `JB105911` and
`JB105912` timed out without a Level result, although Crop `Auto`
straightened both.

| Agreement with Crop Auto | Photos (of 18) |
|---|---|
| within 0.1° | 6 |
| within 0.25° | 7 |
| within 0.5° | 10 |
| within 1.0° | 12 |
| same tilt direction | 17 |

Median absolute difference: 0.48°. Largest: 4.11° (`JB105930`: Crop
Auto +4.36°, Level +0.25°).


## Findings

- The two controls use the same analysis engine: six photos agree to
  within 0.1°, and `JB105901` matches exactly (−0.47°).
- They do not produce the same answer. Results split into exact matches
  and clear disagreements of 0.4–4°, consistent with the two controls
  choosing differently between competing horizontal and vertical cues.
- Crop `Auto` itself varies with crop state: one photo in the working
  catalog carries two Crop `Auto` history steps with different angles
  (−3.39° and −2.74°).


## Boundaries

Evidence produced: one 20-photo event set with event-backdrop geometry
(banners, curtains, angled signage). The spike measures angle agreement
only. It does not judge which control produced the better-looking
result, and it does not claim the agreement rate generalizes to
landscape or architectural sets.


## Decision

Crop `Auto` remains the Operation 1B straightening control, applied
through [`run_crop_auto_straighten.sh`](../../scripts/macos/stage2/run_crop_auto_straighten.sh)
as an unattended foreground run followed by the existing pass/fail
review.

Next validation step, if a background batch is still wanted: review the
largest disagreements side by side. If Upright Level is visually as good
or better there, a plug-in can convert its rotation into a Crop Angle and
turn Upright back off, giving a fully scripted Operation 1B.


## Artifacts

- Plug-in: [`crop-auto-vs-upright-level-spike.lrplugin`](../../lightroom_plugins/crop-auto-vs-upright-level-spike.lrplugin/README.md)
- Comparison script: [`compare_crop_auto_vs_upright_level.py`](../../scripts/python/stage2/spikes/compare_crop_auto_vs_upright_level.py)
- Outputs: [`outputs/lightroom_sdk/`](../../outputs/lightroom_sdk/)
  - `lightroom_sdk_upright_level_probe.json`
  - `lightroom_sdk_crop_auto_angle_record.json`
  - `lightroom_sdk_crop_auto_vs_upright_level_comparison.json`


## Provenance

Research, tooling, and the first run were produced in a Claude Code
session on 2026-09-30:

- Session: `Zen mode for fast culling`
- Session ID: `local_c17fb114-ead3-4150-a16c-46af732df723`
- Link (opens in the Claude desktop app): `claude://claude.ai/epitaxy/local_c17fb114-ead3-4150-a16c-46af732df723`

The first-run outputs were written as CSV and converted to the JSON
artifacts above with values unchanged.
