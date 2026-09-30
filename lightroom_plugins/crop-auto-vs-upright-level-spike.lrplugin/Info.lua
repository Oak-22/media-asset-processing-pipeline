return {
  VERSION = { major = 0, minor = 1, revision = 0, build = 1 },

  LrSdkVersion = 6.0,
  LrSdkMinimumVersion = 6.0,

  LrToolkitIdentifier = "com.julianbuccat.media-asset-pipeline.crop-auto-vs-upright-level-spike",
  LrPluginName = "Media Asset Pipeline - Crop Auto vs Upright Level Spike",
  LrPluginInfoUrl = "https://github.com/Oak-22/media-asset-processing-pipeline",

  LrLibraryMenuItems = {
    {
      title = "1. Probe Upright Level rotation (selected)",
      file = "ProbeUprightLevel.lua",
    },
    {
      title = "2. Record Crop Auto angle (selected)",
      file = "RecordCropAutoAngle.lua",
    },
  },
}
