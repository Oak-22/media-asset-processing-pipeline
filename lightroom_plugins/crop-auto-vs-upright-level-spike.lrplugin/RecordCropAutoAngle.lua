local LrApplication = import "LrApplication"
local LrDialogs = import "LrDialogs"
local LrTasks = import "LrTasks"

local SpikeCommon = require "SpikeCommon"

local OUTPUT_FILE = "lightroom_sdk_crop_auto_angle_record.json"


-- Record each selected photo's Crop Angle after Crop > Auto has been applied.
local function recordSelectedPhotos()
  local photos = LrApplication.activeCatalog():getTargetPhotos()
  if photos == nil or #photos == 0 then
    LrDialogs.message("No selected photos", "Select the Crop Auto branch photos, then run this again.", "info")
    return
  end

  local records = {}
  for _, photo in ipairs(photos) do
    local settings = photo:getDevelopSettings()
    local identity = SpikeCommon.photoIdentity(photo)
    records[#records + 1] = SpikeCommon.object(
      { "asset_key", "file_name", "copy_name", "uuid", "crop_angle_degrees", "perspective_upright" },
      {
        asset_key = identity.asset_key,
        file_name = identity.file_name,
        copy_name = identity.copy_name,
        uuid = identity.uuid,
        crop_angle_degrees = settings.CropAngle or 0,
        perspective_upright = settings.PerspectiveUpright or 0,
      }
    )
  end

  local path = SpikeCommon.writeArtifact(OUTPUT_FILE, SpikeCommon.object(
    { "spike", "artifact", "status", "generated_at_utc", "summary", "notes", "records" },
    {
      spike = SpikeCommon.spikeName,
      artifact = "crop_auto_angle_record",
      status = "complete",
      generated_at_utc = SpikeCommon.utcNow(),
      summary = SpikeCommon.object({ "selected_photo_count" }, { selected_photo_count = #records }),
      notes = SpikeCommon.object(
        { "method", "boundary" },
        {
          method = "Reads CropAngle from getDevelopSettings() after the Crop tool's Auto button was applied per photo.",
          boundary = "Assumes Crop > Auto was the last crop edit on each selected photo; this plug-in does not apply it.",
        }
      ),
      records = records,
    }
  ))

  LrDialogs.message("Crop Auto angles recorded", #records .. " photo(s) recorded to:\n\n" .. path, "info")
end


LrTasks.startAsyncTask(function()
  local ok, err = LrTasks.pcall(recordSelectedPhotos)
  if not ok then
    LrDialogs.message("Crop Auto angle record failed", tostring(err), "critical")
  end
end)
