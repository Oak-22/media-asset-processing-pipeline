# JPEG to RAW Edit Transfer SDK Spike

This Lightroom Classic plug-in runs the calibration pilot for moving
per-photo Develop edits made on camera JPEGs onto the matching RAWs
(RAW + JPEG from the same shutter actuation). It is Spike B ("apply a
global recipe without damaging existing state") of
[Lightroom Edit Recipe Execution Boundary](../../docs/future-work/lightroom-edit-recipe-execution-boundary.md).

The pilot settles, before any batch run:

| Gate | Question |
|---|---|
| P1 | Is a repeat export pixel-identical (measurement floor)? |
| P2 | Do a RAW edit's settings round-trip onto a fresh copy of the same RAW? |
| P3 | Which RAW profile best matches the camera JPEG: Camera Standard, Adobe Color, or Camera Neutral? |
| P4 | How many mired and RAW tint units is one JPEG WB increment? |
| P5 | Tone: re-run Auto Tone on the RAW, or copy the JPEG numbers plus a set-wide offset? |
| P7 | SDK mechanics: profile encoding with no leftover Look, Auto Tone resolution, partial apply, restore |

It also sweeps luminance NR on a central crop to find the value that
roughly matches the JPEG's in-camera noise reduction.


## What it does

```text
selected ARW masters (each with a JPEG sibling in the catalog)
  -> one "Edit Transfer Pilot" virtual copy per ARW and per JPEG
  -> one "Edit Transfer Identity" copy of the ARW whose virtual copy is in collection v01
  -> all copies added to collection "Edit Transfer Pilot"
  -> per copy: apply a variant, export a 16-bit ZIP TIFF (sRGB, 1536 px), read settings back
  -> restore each copy to its starting settings
  -> <event>/Photo/RAW Edit Transfer/pilot/
       pilot_manifest.json
       renders/*.tif
```

Writes go only to the pilot virtual copies. Masters are read, never
written: no write gate is opened on a master, and the manifest records
each master's size and modification time before and after the run.
Virtual-copy settings are never written to XMP, so the masters' files
and sidecars stay unchanged.


## Install

The operator adds the plug-in; agents do not add, remove, or reload it.

1. Open `File > Plug-in Manager`.
2. Click `Add`.
3. Select this folder:

```text
lightroom_plugins/jpeg-to-raw-edit-transfer-spike.lrplugin
```


## Run

1. Optional, recommended: make a virtual copy of one pilot ARW, pick
   `Camera Standard` in the Profile Browser by hand, select that copy,
   and run `Library > Plug-in Extras > 2. Record profile settings
   (selected)`. This records Lightroom's own encoding of the profile as
   the reference for P7. Remove that copy afterwards.
2. Select the pilot ARW masters (not their copies) in Library Grid.
3. Run `Library > Plug-in Extras > 1. Run edit-transfer pilot (selected
   ARW masters)`. It takes several minutes; it can be canceled between
   pairs.
4. Score the renders from the repository root:

```bash
.venv/bin/python scripts/python/stage2/spikes/calibrate_edit_transfer_pilot.py --pilot-root "<event>/Photo/RAW Edit Transfer/pilot"
```

The report goes to `~/Desktop/edit-transfer-pilot-report/` by default.
The scripts refuse to write inside the git checkout, because the pilot
outputs name client folders.

To confirm the masters are byte-identical, hash them before and after
the run with
[`build_edit_transfer_hash_manifest.py`](../../scripts/python/stage2/spikes/build_edit_transfer_hash_manifest.py).


## Boundary

The pilot leaves its virtual copies and collection in the catalog for
visual review; the operator removes them. `applyDevelopSettings` merges
keys and cannot delete them, so a restored copy may keep keys the pilot
added; the manifest lists them.

This spike calibrates the transfer. It does not export recipes, apply
them to imported RAWs, or claim that a RAW will match its JPEG pixel for
pixel.
