local LrApplication = import "LrApplication"
local LrApplicationView = import "LrApplicationView"
local LrDialogs = import "LrDialogs"
local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"
local LrProgressScope = import "LrProgressScope"
local LrTasks = import "LrTasks"

local T = require "TransferCommon"

local PILOT_COPY_NAME = "Edit Transfer Pilot"
local IDENTITY_COPY_NAME = "Edit Transfer Identity"
local PILOT_COLLECTION_NAME = "Edit Transfer Pilot"
local SOURCE_COLLECTION_NAME = "v01"
local HISTORY_PREFIX = "Edit transfer pilot: "

local RENDER_LONG_EDGE = 1536
local CROP_LONG_EDGE = 1024
local AUTO_TONE_TIMEOUT_SECONDS = 30
local AUTO_SENTINEL = -999999

local TONE_KEYS = {
  "Exposure2012", "Contrast2012", "Highlights2012", "Shadows2012",
  "Whites2012", "Blacks2012", "Vibrance", "Saturation",
}
local READBACK_KEYS = {
  "CameraProfile", "CameraProfileDigest", "Look",
  "WhiteBalance", "Temperature", "Tint",
  "IncrementalTemperature", "IncrementalTint",
  "Exposure2012", "Contrast2012", "Highlights2012", "Shadows2012",
  "Whites2012", "Blacks2012", "Vibrance", "Saturation", "AutoTone",
  "LuminanceSmoothing", "CropLeft", "CropRight", "CropTop", "CropBottom", "CropAngle",
}
-- Set-wide RAW-vs-JPEG Auto Tone offset seen on the 6 in-catalog pairs.
local TONE_OFFSET = { Highlights2012 = -20, Shadows2012 = 15, Whites2012 = 4, Blacks2012 = -4 }
local WB_MIRED_STEPS = { -30, -15, 15, 30 }
local WB_TINT_STEPS = { -20, -10, 10, 20 }
local JPEG_INCREMENT_STEPS = { -12, -6, 6, 12 }
local NR_VALUES = { 0, 10, 20, 30, 40, 50 }

local NEUTRAL_TONE = {
  Exposure2012 = 0, Contrast2012 = 0, Highlights2012 = 0, Shadows2012 = 0,
  Whites2012 = 0, Blacks2012 = 0, Vibrance = 0, Saturation = 0,
  Texture = 0, Clarity2012 = 0, Dehaze = 0,
}
local FULL_FRAME = { CropLeft = 0, CropRight = 1, CropTop = 0, CropBottom = 1, CropAngle = 0 }
-- Central 20% x 20% patch for noise matching, exported near 1:1 of the JPEG.
local NOISE_CROP = {
  CropLeft = 0.4, CropRight = 0.6, CropTop = 0.4, CropBottom = 0.6,
  CropAngle = 0, CropConstrainAspectRatio = false,
}


local function clamp(value, low, high)
  return math.max(low, math.min(high, value))
end


local function kelvinWithMiredShift(kelvin, miredShift)
  return math.floor(1e6 / (1e6 / kelvin + miredShift) + 0.5)
end


-- Virtual copies of the masters, keyed by master localIdentifier then copy
-- name. Read from the masters' folder (which lists virtual copies) rather
-- than the master's `virtualCopies` key, which can lag a fresh copy.
local function copiesInFolder(catalog, folderPath)
  local folder = catalog:getFolderByPath(folderPath)
  if folder == nil then
    error("Folder not in catalog: " .. folderPath)
  end
  local photos = folder:getPhotos(false)
  local metadata = catalog:batchGetRawMetadata(photos, { "isVirtualCopy", "masterPhoto" })
  local byMaster = {}
  for _, photo in ipairs(photos) do
    local row = metadata[photo]
    if row and row.isVirtualCopy and row.masterPhoto then
      local copyName = T.safeFormattedMetadata(photo, "copyName") or T.safeRawMetadata(photo, "copyName")
      if copyName then
        local key = row.masterPhoto.localIdentifier
        byMaster[key] = byMaster[key] or {}
        byMaster[key][copyName] = byMaster[key][copyName] or photo
      end
    end
  end
  return byMaster, folder
end


local function lookupCopies(catalog, folderPath, masters, copyName)
  local byMaster = copiesInFolder(catalog, folderPath)
  local copies, missing = {}, {}
  for _, master in ipairs(masters) do
    local copy = (byMaster[master.localIdentifier] or {})[copyName]
    if copy then
      copies[master.localIdentifier] = copy
    else
      missing[#missing + 1] = master
    end
  end
  return copies, missing
end


local function isInCollectionNamed(photo, collectionName)
  local ok, collections = LrTasks.pcall(function()
    return photo:getContainedCollections()
  end)
  if not ok then
    return false
  end
  for _, collection in ipairs(collections or {}) do
    if collection:getName() == collectionName then
      return true
    end
  end
  return false
end


-- createVirtualCopies acts on the current selection, so it must run outside
-- a write gate with the masters selected in the Library grid. The masters'
-- folder becomes the active source so JPEG and ARW masters are both visible;
-- the caller restores the operator's sources afterwards.
local function ensureCopies(catalog, folderPath, masters, copyName)
  local copies, missing = lookupCopies(catalog, folderPath, masters, copyName)

  if #missing > 0 then
    local _, folder = copiesInFolder(catalog, folderPath)
    LrApplicationView.switchToModule("library")
    LrTasks.pcall(function()
      LrApplicationView.showView("grid")
    end)
    catalog:setActiveSources({ folder })
    LrTasks.sleep(0.5)
    catalog:setSelectedPhotos(missing[1], missing)
    LrTasks.sleep(0.5)
    catalog:createVirtualCopies(copyName)

    local waited = 0
    repeat
      LrTasks.sleep(0.5)
      waited = waited + 0.5
      copies, missing = lookupCopies(catalog, folderPath, masters, copyName)
    until #missing == 0 or waited >= 10
  end

  if #missing > 0 then
    local names = {}
    for _, master in ipairs(missing) do
      names[#names + 1] = tostring(T.assetKey(master)) .. "." .. tostring(T.safeRawMetadata(master, "fileFormat"))
    end
    error("Could not create a '" .. copyName .. "' virtual copy of: " .. table.concat(names, ", "))
  end
  return copies
end


local function findJpegSibling(catalog, rawPath)
  local stem = LrPathUtils.removeExtension(rawPath)
  for _, extension in ipairs({ "JPG", "jpg", "JPEG", "jpeg" }) do
    local photo = catalog:findPhotoByPath(stem .. "." .. extension)
    if photo then
      return photo
    end
  end
  return nil
end


local function resolvePairs(catalog, selected)
  local pairs_, problems = {}, {}
  for _, photo in ipairs(selected) do
    local key = T.assetKey(photo) or "?"
    if T.safeRawMetadata(photo, "isVirtualCopy") then
      problems[#problems + 1] = key .. ": is a virtual copy (select ARW masters)"
    elseif T.safeRawMetadata(photo, "fileFormat") ~= "RAW" then
      problems[#problems + 1] = key .. ": not a RAW master"
    else
      local rawPath = photo:getRawMetadata("path")
      local jpeg = findJpegSibling(catalog, rawPath)
      if jpeg == nil then
        problems[#problems + 1] = key .. ": no JPEG sibling in the catalog"
      elseif T.safeRawMetadata(jpeg, "isVirtualCopy") or T.safeRawMetadata(jpeg, "fileFormat") ~= "JPG" then
        problems[#problems + 1] = key .. ": JPEG sibling is not a JPEG master"
      else
        pairs_[#pairs_ + 1] = {
          assetKey = key,
          raw = photo,
          jpeg = jpeg,
          rawPath = rawPath,
          jpegPath = jpeg:getRawMetadata("path"),
        }
      end
    end
  end
  return pairs_, problems
end


local function masterFileStats(pair)
  local xmpPath = LrPathUtils.replaceExtension(pair.rawPath, "xmp")
  return T.object(
    { "raw", "raw_xmp", "jpeg" },
    {
      raw = T.fileStat(pair.rawPath),
      raw_xmp = T.fileStat(xmpPath),
      jpeg = T.fileStat(pair.jpegPath),
    }
  )
end


local function waitForAutoTone(photo)
  local waited = 0
  while waited < AUTO_TONE_TIMEOUT_SECONDS do
    local settings = photo:getDevelopSettings()
    if settings.AutoTone ~= true and settings.Exposure2012 ~= nil and settings.Exposure2012 ~= AUTO_SENTINEL then
      return settings, waited
    end
    LrTasks.sleep(0.25)
    waited = waited + 0.25
  end
  error("Auto Tone did not resolve within " .. AUTO_TONE_TIMEOUT_SECONDS .. " s")
end


local function isExpectedChange(spec, key)
  if spec.payload ~= nil and spec.payload[key] ~= nil then
    return true
  end
  if spec.autoTone then
    if key == "AutoTone" or key:find("^AutoToneDigest") then
      return true
    end
    for _, toneKey in ipairs(TONE_KEYS) do
      if key == toneKey then
        return true
      end
    end
  end
  return false
end


-- Apply an optional payload, export one render, and record what Lightroom
-- stored. `unexpected_changed_keys` lists keys that changed although they
-- were not in the payload (the partial-apply check in P7).
local function renderVariant(ctx, record, photo, spec)
  local entry = T.object(
    {
      "variant", "group", "side", "file", "long_edge", "payload",
      "auto_tone_wait_seconds", "unexpected_changed_keys",
      "changed_during_export_keys", "readback", "error",
    },
    {
      variant = spec.variant,
      group = spec.group,
      side = spec.side,
      long_edge = spec.longEdge or RENDER_LONG_EDGE,
      payload = spec.payload,
    }
  )

  local ok, err = LrTasks.pcall(function()
    local before = photo:getDevelopSettings()
    if spec.payload then
      T.applySettings(ctx.catalog, photo, spec.payload, HISTORY_PREFIX .. spec.variant)
    end
    if spec.autoTone then
      T.applySettings(ctx.catalog, photo, { AutoTone = true }, HISTORY_PREFIX .. spec.variant .. " (Auto)", true)
      local _, waited = waitForAutoTone(photo)
      entry.auto_tone_wait_seconds = waited
    end
    local applied = photo:getDevelopSettings()

    local unexpected = {}
    for _, key in ipairs(T.changedKeys(before, applied)) do
      if not isExpectedChange(spec, key) then
        unexpected[#unexpected + 1] = key
      end
    end
    entry.unexpected_changed_keys = unexpected

    entry.file = T.exportRender(photo, ctx.renderDir, record.asset_key .. "__" .. spec.variant, entry.long_edge)
    local exported = photo:getDevelopSettings()
    entry.changed_during_export_keys = T.changedKeys(applied, exported)
    entry.readback = T.pick(exported, READBACK_KEYS)
  end)
  if not ok then
    entry.error = tostring(err)
  end
  record.renders[#record.renders + 1] = entry
  ctx.progress:setPortionComplete(ctx.step, ctx.totalSteps)
  ctx.step = ctx.step + 1
  return entry
end


-- Restore a copy to its starting settings. applyDevelopSettings merges and
-- cannot delete keys, so keys the pilot added are reported, not removed.
local function restoreCopy(ctx, photo, initial)
  local payload = T.merge(FULL_FRAME, initial)
  local result = T.object({ "ok", "differing_keys", "error" }, {})
  local ok, err = LrTasks.pcall(function()
    T.applySettings(ctx.catalog, photo, payload, HISTORY_PREFIX .. "restore")
    result.differing_keys = T.changedKeys(initial, photo:getDevelopSettings())
    result.ok = #result.differing_keys == 0
  end)
  if not ok then
    result.ok = false
    result.error = tostring(err)
  end
  return result
end


local function runJpegSide(ctx, record, copy)
  local initial = copy:getDevelopSettings()
  record.jpeg_initial_settings = initial

  renderVariant(ctx, record, copy, { variant = "jpg_asis", group = "bases", side = "jpeg" })
  local resolved = copy:getDevelopSettings()
  record.jpeg_auto_tone = T.pick(resolved, TONE_KEYS)

  local zero = T.merge(NEUTRAL_TONE, FULL_FRAME, {
    WhiteBalance = "As Shot", IncrementalTemperature = 0, IncrementalTint = 0,
  })
  renderVariant(ctx, record, copy, { variant = "jpg_zero", group = "bases", side = "jpeg", payload = zero })

  for _, axis in ipairs({ "temp", "tint" }) do
    for _, step in ipairs(JPEG_INCREMENT_STEPS) do
      local temperature = axis == "temp" and step or 0
      local tint = axis == "tint" and step or 0
      renderVariant(ctx, record, copy, {
        variant = string.format("jpg_wb_%s%+d", axis, step),
        group = "jpeg_wb_grid",
        side = "jpeg",
        payload = T.merge(zero, {
          WhiteBalance = "Custom",
          IncrementalTemperature = temperature, IncrementalTint = tint,
          CustomIncrementalTemperature = temperature, CustomIncrementalTint = tint,
        }),
      })
    end
  end

  renderVariant(ctx, record, copy, {
    variant = "jpg_asis_noise_crop", group = "noise", side = "jpeg",
    payload = T.merge(FULL_FRAME, initial, NOISE_CROP), longEdge = CROP_LONG_EDGE,
  })

  record.jpeg_restore = restoreCopy(ctx, copy, initial)
end


local function runRawSide(ctx, record, copy)
  local initial = copy:getDevelopSettings()
  record.raw_initial_settings = initial

  local asShot = { WhiteBalance = "As Shot", Temperature = initial.Temperature, Tint = initial.Tint }
  record.raw_as_shot = T.object({ "white_balance", "temperature", "tint" }, {
    white_balance = initial.WhiteBalance, temperature = initial.Temperature, tint = initial.Tint,
  })
  if initial.WhiteBalance ~= "As Shot" or type(initial.Temperature) ~= "number" then
    error("RAW copy does not start at As Shot WB; cannot anchor the WB grid")
  end
  local hasAdobeColor = type(initial.Look) == "table" and initial.Look.Name == "Adobe Color"

  local profiles = {
    camera_standard = { CameraProfile = "Camera Standard", CameraProfileDigest = "", Look = {} },
    camera_neutral = { CameraProfile = "Camera Neutral", CameraProfileDigest = "", Look = {} },
  }
  local base = T.merge(NEUTRAL_TONE, FULL_FRAME, asShot, {
    LuminanceSmoothing = 0, LensProfileEnable = 1, AutoLateralCA = 1,
  })
  local csBase = T.merge(base, profiles.camera_standard)

  -- P3 profiles and P1 determinism.
  renderVariant(ctx, record, copy, { variant = "raw_camera_standard", group = "raw_profiles", side = "raw", payload = csBase })
  renderVariant(ctx, record, copy, { variant = "raw_camera_standard_repeat", group = "determinism", side = "raw" })
  if hasAdobeColor then
    renderVariant(ctx, record, copy, {
      variant = "raw_adobe_color", group = "raw_profiles", side = "raw",
      payload = T.merge(base, T.pick(initial, { "CameraProfile", "CameraProfileDigest", "Look" })),
    })
  end
  renderVariant(ctx, record, copy, {
    variant = "raw_camera_neutral", group = "raw_profiles", side = "raw",
    payload = T.merge(base, profiles.camera_neutral),
  })

  -- P7 profile encodings: does the name resolve without a digest, and does a
  -- leftover Adobe Color Look override the profile?
  if hasAdobeColor then
    renderVariant(ctx, record, copy, {
      variant = "p7_cs_digest_kept", group = "p7_profile", side = "raw",
      payload = T.merge(base, { CameraProfile = "Camera Standard", CameraProfileDigest = initial.CameraProfileDigest, Look = {} }),
    })
    renderVariant(ctx, record, copy, {
      variant = "p7_cs_look_kept", group = "p7_profile", side = "raw",
      payload = T.merge(base, { CameraProfile = "Camera Standard", CameraProfileDigest = "", Look = T.deepCopy(initial.Look) }),
    })
    renderVariant(ctx, record, copy, {
      variant = "p7_adobe_standard_no_look", group = "p7_profile", side = "raw",
      payload = T.merge(base, { CameraProfile = "Adobe Standard", CameraProfileDigest = initial.CameraProfileDigest, Look = {} }),
    })
  end

  -- P4 RAW WB grid around As Shot on Camera Standard.
  for _, mired in ipairs(WB_MIRED_STEPS) do
    renderVariant(ctx, record, copy, {
      variant = string.format("raw_wb_mired%+d", mired), group = "raw_wb_grid", side = "raw",
      payload = T.merge(csBase, {
        WhiteBalance = "Custom",
        Temperature = kelvinWithMiredShift(initial.Temperature, mired),
        Tint = initial.Tint,
      }),
    })
  end
  for _, tint in ipairs(WB_TINT_STEPS) do
    renderVariant(ctx, record, copy, {
      variant = string.format("raw_wb_tint%+d", tint), group = "raw_wb_grid", side = "raw",
      payload = T.merge(csBase, {
        WhiteBalance = "Custom", Temperature = initial.Temperature,
        Tint = clamp(initial.Tint + tint, -150, 150),
      }),
    })
  end

  -- P5 tone methods on Camera Standard + As Shot.
  local jpegTone = record.jpeg_auto_tone
  local jpegToneUsable = jpegTone ~= nil
  for _, key in ipairs(TONE_KEYS) do
    if jpegTone == nil or type(jpegTone[key]) ~= "number" or jpegTone[key] == AUTO_SENTINEL then
      jpegToneUsable = false
    end
  end
  if jpegToneUsable then
    renderVariant(ctx, record, copy, {
      variant = "tone_verbatim", group = "raw_tone", side = "raw",
      payload = T.merge(csBase, jpegTone),
    })
    local offset = T.deepCopy(jpegTone)
    for key, delta in pairs(TONE_OFFSET) do
      offset[key] = clamp(offset[key] + delta, -100, 100)
    end
    renderVariant(ctx, record, copy, {
      variant = "tone_offset", group = "raw_tone", side = "raw",
      payload = T.merge(csBase, offset),
    })
  else
    record.notes[#record.notes + 1] = "JPEG Auto Tone values unresolved; verbatim and offset variants skipped"
  end
  local auto = renderVariant(ctx, record, copy, {
    variant = "tone_auto", group = "raw_tone", side = "raw", payload = csBase, autoTone = true,
  })
  record.raw_auto_tone = auto.readback and T.pick(auto.readback, TONE_KEYS) or nil

  -- Noise matching: Auto-toned Camera Standard, central crop, NR sweep.
  for _, amount in ipairs(NR_VALUES) do
    renderVariant(ctx, record, copy, {
      variant = string.format("raw_nr%02d_noise_crop", amount), group = "noise", side = "raw",
      payload = T.merge(NOISE_CROP, { LuminanceSmoothing = amount }), longEdge = CROP_LONG_EDGE,
    })
  end

  record.raw_restore = restoreCopy(ctx, copy, initial)
end


-- P2: the v01 RAW edit's settings applied to a fresh copy of the same ARW.
local function runIdentity(ctx, master, source, copy)
  local record = T.object(
    { "asset_key", "source", "copy", "missing_or_different_keys", "renders", "notes" },
    {
      asset_key = T.assetKey(master),
      source = T.photoIdentity(source),
      copy = T.photoIdentity(copy),
      renders = {},
      notes = {},
    }
  )
  local sourceSettings = source:getDevelopSettings()
  renderVariant(ctx, record, source, { variant = "id_source", group = "identity", side = "raw" })
  renderVariant(ctx, record, copy, { variant = "id_copy", group = "identity", side = "raw", payload = sourceSettings })
  record.missing_or_different_keys = T.changedKeys(sourceSettings, copy:getDevelopSettings())
  return record
end


local function runPilot()
  local catalog = LrApplication.activeCatalog()
  local selected = catalog:getTargetPhotos()
  if selected == nil or #selected == 0 then
    LrDialogs.message("No selected photos", "Select the ARW masters of the pilot pairs, then run this again.", "info")
    return
  end
  local originalActive = catalog:getTargetPhoto()

  local pilotPairs, problems = resolvePairs(catalog, selected)
  if #problems > 0 then
    LrDialogs.message("Pilot selection rejected", table.concat(problems, "\n"), "critical")
    return
  end

  local workingRoot = T.workingRootFor(pilotPairs[1].rawPath)
  for _, pair in ipairs(pilotPairs) do
    if T.workingRootFor(pair.rawPath) ~= workingRoot then
      LrDialogs.message("Pilot selection rejected", "Selected ARWs come from more than one event folder.", "critical")
      return
    end
  end
  local pilotRoot = LrPathUtils.child(workingRoot, "pilot")
  local renderDir = LrPathUtils.child(pilotRoot, "renders")
  T.assertOutsideRepo(pilotRoot)
  LrFileUtils.createAllDirectories(renderDir)

  local before = {}
  for _, pair in ipairs(pilotPairs) do
    before[pair.assetKey] = masterFileStats(pair)
  end

  -- Identity source: an ARW whose own (non-pilot) virtual copy sits in a v01 collection.
  local folderPath = LrPathUtils.parent(pilotPairs[1].rawPath)
  for _, pair in ipairs(pilotPairs) do
    if LrPathUtils.parent(pair.rawPath) ~= folderPath or LrPathUtils.parent(pair.jpegPath) ~= folderPath then
      LrDialogs.message("Pilot selection rejected", "Each ARW and its JPEG must share one folder.", "critical")
      return
    end
  end
  local existingCopies = copiesInFolder(catalog, folderPath)
  local identityMaster, identitySource
  for _, pair in ipairs(pilotPairs) do
    for copyName, vc in pairs(existingCopies[pair.raw.localIdentifier] or {}) do
      if copyName ~= PILOT_COPY_NAME and copyName ~= IDENTITY_COPY_NAME
        and isInCollectionNamed(vc, SOURCE_COLLECTION_NAME) then
        identityMaster, identitySource = pair.raw, vc
      end
    end
  end

  local masters = {}
  for _, pair in ipairs(pilotPairs) do
    masters[#masters + 1] = pair.raw
    masters[#masters + 1] = pair.jpeg
  end
  local originalSources = catalog:getActiveSources()
  local copies = ensureCopies(catalog, folderPath, masters, PILOT_COPY_NAME)
  local identityCopy
  if identityMaster then
    identityCopy = ensureCopies(catalog, folderPath, { identityMaster }, IDENTITY_COPY_NAME)[identityMaster.localIdentifier]
  end

  catalog:withWriteAccessDo("Edit transfer pilot collection", function()
    local collection = catalog:createCollection(PILOT_COLLECTION_NAME, nil, true)
    local members = {}
    for _, copy in pairs(copies) do
      members[#members + 1] = copy
    end
    if identityCopy then
      members[#members + 1] = identityCopy
    end
    collection:addPhotos(members)
  end, { timeout = 30 })

  local ctx = {
    catalog = catalog,
    renderDir = renderDir,
    progress = LrProgressScope({ title = "Edit transfer pilot" }),
    step = 0,
    totalSteps = #pilotPairs * 40 + 2,
  }

  local manifest = T.object(
    {
      "spike", "artifact", "status", "generated_at_utc", "finished_at_utc",
      "lightroom_version", "settings", "pairs", "identity",
      "master_files_before", "master_files_after",
    },
    {
      spike = T.spikeName,
      artifact = "pilot_manifest",
      status = "running",
      generated_at_utc = T.utcNow(),
      lightroom_version = LrApplication.versionString(),
      settings = T.object(
        { "render_long_edge", "crop_long_edge", "noise_crop", "tone_offset", "wb_mired_steps", "wb_tint_steps", "jpeg_increment_steps", "nr_values" },
        {
          render_long_edge = RENDER_LONG_EDGE,
          crop_long_edge = CROP_LONG_EDGE,
          noise_crop = NOISE_CROP,
          tone_offset = TONE_OFFSET,
          wb_mired_steps = WB_MIRED_STEPS,
          wb_tint_steps = WB_TINT_STEPS,
          jpeg_increment_steps = JPEG_INCREMENT_STEPS,
          nr_values = NR_VALUES,
        }
      ),
      pairs = {},
      master_files_before = before,
    }
  )
  local manifestPath = LrPathUtils.child(pilotRoot, "pilot_manifest.json")

  for _, pair in ipairs(pilotPairs) do
    if ctx.progress:isCanceled() then
      break
    end
    ctx.progress:setCaption(pair.assetKey)
    local record = T.object(
      {
        "asset_key", "raw_master_path", "jpeg_master_path", "raw_copy", "jpeg_copy",
        "raw_as_shot", "jpeg_auto_tone", "raw_auto_tone", "jpeg_restore", "raw_restore",
        "notes", "error", "renders", "jpeg_initial_settings", "raw_initial_settings",
      },
      {
        asset_key = pair.assetKey,
        raw_master_path = pair.rawPath,
        jpeg_master_path = pair.jpegPath,
        raw_copy = T.photoIdentity(copies[pair.raw.localIdentifier]),
        jpeg_copy = T.photoIdentity(copies[pair.jpeg.localIdentifier]),
        notes = {},
        renders = {},
      }
    )
    local ok, err = LrTasks.pcall(function()
      runJpegSide(ctx, record, copies[pair.jpeg.localIdentifier])
      runRawSide(ctx, record, copies[pair.raw.localIdentifier])
    end)
    if not ok then
      record.error = tostring(err)
    end
    manifest.pairs[#manifest.pairs + 1] = record
    T.writeJson(manifestPath, manifest)
  end

  if identityMaster and not ctx.progress:isCanceled() then
    local ok, result = LrTasks.pcall(runIdentity, ctx, identityMaster, identitySource, identityCopy)
    manifest.identity = ok and result or T.object({ "error" }, { error = tostring(result) })
  else
    manifest.identity = T.object({ "error" }, { error = "No selected ARW has a virtual copy in collection " .. SOURCE_COLLECTION_NAME })
  end

  local after = {}
  for _, pair in ipairs(pilotPairs) do
    after[pair.assetKey] = masterFileStats(pair)
  end
  manifest.master_files_after = after
  manifest.status = ctx.progress:isCanceled() and "canceled" or "complete"
  manifest.finished_at_utc = T.utcNow()
  T.writeJson(manifestPath, manifest)
  ctx.progress:done()

  LrTasks.pcall(function()
    catalog:setActiveSources(originalSources)
    if originalActive then
      catalog:setSelectedPhotos(originalActive, selected)
    end
  end)

  local failed = 0
  for _, record in ipairs(manifest.pairs) do
    if record.error then
      failed = failed + 1
    end
    for _, entry in ipairs(record.renders) do
      if entry.error then
        failed = failed + 1
      end
    end
  end
  LrDialogs.message(
    "Edit transfer pilot " .. manifest.status,
    #manifest.pairs .. " pair(s) processed, " .. failed .. " error(s).\n\nManifest:\n" .. manifestPath,
    failed == 0 and "info" or "warning"
  )
end


LrTasks.startAsyncTask(function()
  local ok, err = LrTasks.pcall(runPilot)
  if not ok then
    LrDialogs.message("Edit transfer pilot failed", tostring(err), "critical")
  end
end)
