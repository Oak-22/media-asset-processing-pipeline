local LrApplication = import "LrApplication"
local LrDialogs = import "LrDialogs"
local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"
local LrTasks = import "LrTasks"

local T = require "TransferCommon"

-- Read-only: records how Lightroom stores a profile the operator picked in
-- the Profile Browser, as the reference for the pilot's SDK encoding.
local function recordSelected()
  local catalog = LrApplication.activeCatalog()
  local photos = catalog:getTargetPhotos()
  if photos == nil or #photos == 0 then
    LrDialogs.message("No selected photos", "Select the photo(s) whose profile you set by hand, then run this again.", "info")
    return
  end

  local pilotRoot = LrPathUtils.child(T.workingRootFor(photos[1]:getRawMetadata("path")), "pilot")
  T.assertOutsideRepo(pilotRoot)
  LrFileUtils.createAllDirectories(pilotRoot)

  local records = {}
  for _, photo in ipairs(photos) do
    local settings = photo:getDevelopSettings()
    records[#records + 1] = T.object(
      { "identity", "camera_profile", "camera_profile_digest", "look", "settings" },
      {
        identity = T.photoIdentity(photo),
        camera_profile = settings.CameraProfile,
        camera_profile_digest = settings.CameraProfileDigest,
        look = settings.Look,
        settings = settings,
      }
    )
  end

  local path = LrPathUtils.child(pilotRoot, "profile_reference.json")
  T.writeJson(path, T.object(
    { "spike", "artifact", "generated_at_utc", "records" },
    {
      spike = T.spikeName,
      artifact = "profile_reference",
      generated_at_utc = T.utcNow(),
      records = records,
    }
  ))
  LrDialogs.message("Profile settings recorded", #records .. " photo(s) recorded to:\n\n" .. path, "info")
end


LrTasks.startAsyncTask(function()
  local ok, err = LrTasks.pcall(recordSelected)
  if not ok then
    LrDialogs.message("Recording profile settings failed", tostring(err), "critical")
  end
end)
