# Develop Settings SDK Spike

This Lightroom Classic plug-in is a proof-of-capability spike for reading
Develop settings through the Lightroom SDK.

It does one thing:

```text
selected Lightroom photo(s)
  -> Lightroom SDK getDevelopSettings()
  -> outputs/lightroom_sdk/lightroom_sdk_selected_develop_settings_export.json
```

The goal is to prove that Lightroom can expose Develop state from inside
the GUI and write a repository artifact that can be compared against the
pipeline's XMP-derived JSON outputs.


## Install

In Lightroom Classic:

1. Open `File > Plug-in Manager`.
2. Click `Add`.
3. Select this folder:

```text
lightroom_plugins/develop-settings-spike.lrplugin
```

Do not copy the plug-in folder elsewhere for this spike. The export path
is derived from the plug-in's location inside this repository.


## Run

1. Select one or more photos in Lightroom.
2. Run `Library > Plug-in Extras > Export selected Develop settings`.
3. Inspect the generated artifact:

```text
outputs/lightroom_sdk/lightroom_sdk_selected_develop_settings_export.json
```


## Boundary

This spike only reads Develop settings. It does not apply edits, create
masks, modify XMP sidecars, or claim that Lightroom AI masking is
scriptable.

Records identify each photo by `asset_key`, `file_name`, `copy_name`,
and `uuid`. The artifact stores repo-relative paths only: source file
paths are not written because they expose local volume and client
folder names in a public repository.

The next comparison step is to run the repository's Python XMP extractor
against the same selected asset(s) and check whether the SDK-exposed
Develop state matches the sidecar-derived state.
