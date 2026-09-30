local LrApplication = import "LrApplication"
local LrDialogs = import "LrDialogs"
local LrProgressScope = import "LrProgressScope"
local LrTasks = import "LrTasks"

local SpikeCommon = require "SpikeCommon"

local OUTPUT_FILE = "lightroom_sdk_upright_level_probe.json"
local ANALYSIS_TIMEOUT_SECONDS = 10
local UPRIGHT_LEVEL = 3


-- Turn on Transform > Upright Level, wait for Lightroom to store its analysis,
-- record the Level rotation, then restore the photo's prior Upright mode.
local function probePhoto(catalog, photo)
  local prior = photo:getDevelopSettings()
  local hadMatricesBefore = prior.UprightTransform_3 ~= nil

  catalog:withWriteAccessDo("Upright Level probe", function()
    photo:applyDevelopSettings({ EnableTransform = true, PerspectiveUpright = UPRIGHT_LEVEL })
  end, { timeout = 30 })

  local rotation, waited = nil, 0
  repeat
    LrTasks.sleep(0.25)
    waited = waited + 0.25
    local settings = photo:getDevelopSettings()
    if settings.PerspectiveUpright == UPRIGHT_LEVEL then
      rotation = SpikeCommon.levelRotationDegrees(settings)
    end
  until rotation ~= nil or waited >= ANALYSIS_TIMEOUT_SECONDS

  catalog:withWriteAccessDo("Upright Level probe revert", function()
    photo:applyDevelopSettings({ PerspectiveUpright = prior.PerspectiveUpright or 0 })
  end, { timeout = 30 })

  local identity = SpikeCommon.photoIdentity(photo)
  return SpikeCommon.object(
    {
      "asset_key", "file_name", "copy_name", "uuid",
      "prior_perspective_upright", "had_upright_matrices_before",
      "upright_level_rotation_degrees", "predicted_crop_angle_degrees",
      "analysis_wait_seconds",
    },
    {
      asset_key = identity.asset_key,
      file_name = identity.file_name,
      copy_name = identity.copy_name,
      uuid = identity.uuid,
      prior_perspective_upright = prior.PerspectiveUpright or 0,
      had_upright_matrices_before = hadMatricesBefore,
      upright_level_rotation_degrees = SpikeCommon.round(rotation),
      -- Crop Angle uses the opposite sign convention to the Level matrix.
      predicted_crop_angle_degrees = rotation and SpikeCommon.round(-rotation) or nil,
      analysis_wait_seconds = waited,
    }
  )
end


local function probeSelectedPhotos()
  local catalog = LrApplication.activeCatalog()
  local photos = catalog:getTargetPhotos()
  if photos == nil or #photos == 0 then
    LrDialogs.message("No selected photos", "Select the Upright Level branch photos, then run this again.", "info")
    return
  end

  local progress = LrProgressScope({ title = "Probing Upright Level rotation" })
  local records, recorded = {}, 0
  for index, photo in ipairs(photos) do
    if progress:isCanceled() then
      break
    end
    progress:setPortionComplete(index - 1, #photos)
    local record = probePhoto(catalog, photo)
    if record.upright_level_rotation_degrees ~= nil then
      recorded = recorded + 1
    end
    records[#records + 1] = record
  end
  progress:done()

  local path = SpikeCommon.writeArtifact(OUTPUT_FILE, SpikeCommon.object(
    { "spike", "artifact", "status", "generated_at_utc", "summary", "notes", "records" },
    {
      spike = SpikeCommon.spikeName,
      artifact = "upright_level_probe",
      status = "complete",
      generated_at_utc = SpikeCommon.utcNow(),
      summary = SpikeCommon.object(
        { "selected_photo_count", "level_rotation_recorded_count", "level_rotation_missing_count" },
        {
          selected_photo_count = #records,
          level_rotation_recorded_count = recorded,
          level_rotation_missing_count = #records - recorded,
        }
      ),
      notes = SpikeCommon.object(
        { "method", "boundary" },
        {
          method = "Per photo: apply Transform > Upright Level, read UprightTransform_3 from getDevelopSettings(), convert it to a rotation, then restore the prior Upright mode.",
          boundary = "Records Lightroom's Level analysis only. It does not press the Crop tool's Auto button, which the SDK does not expose.",
        }
      ),
      records = records,
    }
  ))

  LrDialogs.message("Upright Level probe complete", recorded .. " of " .. #records .. " photo(s) recorded to:\n\n" .. path, "info")
end


LrTasks.startAsyncTask(function()
  local ok, err = LrTasks.pcall(probeSelectedPhotos)
  if not ok then
    LrDialogs.message("Upright Level probe failed", tostring(err), "critical")
  end
end)
