# Crop Auto vs Upright Level SDK Spike

This Lightroom Classic plug-in is a proof-of-capability spike for
testing whether Transform > Upright Level can stand in for the Crop
tool's Auto straighten button, which the Lightroom SDK cannot invoke.

It does two things:

```text
selected Upright Level branch photo(s)
  -> apply Upright Level, read UprightTransform_3, restore prior Upright mode
  -> outputs/lightroom_sdk/lightroom_sdk_upright_level_probe.json

selected Crop Auto branch photo(s)
  -> read CropAngle after Crop > Auto
  -> outputs/lightroom_sdk/lightroom_sdk_crop_auto_angle_record.json
```

The two artifacts are compared by
[`compare_crop_auto_vs_upright_level.py`](../../scripts/python/stage2/spikes/compare_crop_auto_vs_upright_level.py).
Findings are recorded in
[Crop Auto vs Upright Level Spike](../../docs/future-work/crop-auto-vs-upright-level-spike.md).


## Install

In Lightroom Classic:

1. Open `File > Plug-in Manager`.
2. Click `Add`.
3. Select this folder:

```text
lightroom_plugins/crop-auto-vs-upright-level-spike.lrplugin
```

Do not copy the plug-in folder elsewhere. The output path is derived
from the plug-in's location inside this repository.


## Run

Use two Virtual Copy branches of the same originals, one copy per
original in each branch:

1. Select the Upright Level branch and run
   `Library > Plug-in Extras > 1. Probe Upright Level rotation (selected)`.
2. Apply Crop > Auto to each photo in the Crop Auto branch, for example
   with
   [`run_crop_auto_straighten.sh`](../../scripts/macos/stage2/run_crop_auto_straighten.sh).
3. Select the Crop Auto branch and run
   `Library > Plug-in Extras > 2. Record Crop Auto angle (selected)`.
4. Run the comparison script from the repository root:

```bash
python3 scripts/python/stage2/spikes/compare_crop_auto_vs_upright_level.py
```


## Boundary

The probe leaves each photo's Upright mode as it found it, so the Level
branch shows a Level step followed by a revert step in History.

This spike measures Lightroom's Level analysis. It does not press the
Crop tool's Auto button, write CropAngle, or claim that Level and Crop
Auto produce the same result.
