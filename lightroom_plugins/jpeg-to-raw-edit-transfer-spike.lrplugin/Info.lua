return {
  VERSION = { major = 0, minor = 1, revision = 0, build = 1 },

  LrSdkVersion = 13.0,
  LrSdkMinimumVersion = 13.0,

  LrToolkitIdentifier = "com.julianbuccat.media-asset-pipeline.jpeg-to-raw-edit-transfer-spike",
  LrPluginName = "Media Asset Pipeline - JPEG to RAW Edit Transfer Spike",
  LrPluginInfoUrl = "https://github.com/Oak-22/media-asset-processing-pipeline",

  LrLibraryMenuItems = {
    {
      title = "1. Run edit-transfer pilot (selected ARW masters)",
      file = "RunPilot.lua",
    },
    {
      title = "2. Record profile settings (selected)",
      file = "RecordProfileSettings.lua",
    },
  },
}
