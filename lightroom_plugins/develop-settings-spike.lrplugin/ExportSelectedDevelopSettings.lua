local LrApplication = import "LrApplication"
local LrDialogs = import "LrDialogs"
local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"
local LrTasks = import "LrTasks"


local function sortedKeys(tbl)
  local keys = {}
  for key, _ in pairs(tbl) do
    keys[#keys + 1] = key
  end
  table.sort(keys, function(left, right)
    return tostring(left) < tostring(right)
  end)
  return keys
end


local function escapeJsonString(value)
  local replacements = {
    ['"'] = '\\"',
    ["\\"] = "\\\\",
    ["\b"] = "\\b",
    ["\f"] = "\\f",
    ["\n"] = "\\n",
    ["\r"] = "\\r",
    ["\t"] = "\\t",
  }
  return '"' .. tostring(value):gsub('[%z\1-\31\\"]', function(character)
    return replacements[character] or string.format("\\u%04x", character:byte())
  end) .. '"'
end


local function isArray(tbl)
  local maxIndex = 0
  local count = 0
  for key, _ in pairs(tbl) do
    if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
      return false
    end
    if key > maxIndex then
      maxIndex = key
    end
    count = count + 1
  end
  return maxIndex == count
end


local function jsonEncode(value, indentLevel)
  indentLevel = indentLevel or 0
  local valueType = type(value)

  if value == nil then
    return "null"
  end

  if valueType == "boolean" then
    return value and "true" or "false"
  end

  if valueType == "number" then
    return tostring(value)
  end

  if valueType == "string" then
    return escapeJsonString(value)
  end

  if valueType ~= "table" then
    return escapeJsonString("<" .. valueType .. ">")
  end

  local indent = string.rep("  ", indentLevel)
  local childIndent = string.rep("  ", indentLevel + 1)
  local parts = {}

  if isArray(value) then
    for index = 1, #value do
      parts[#parts + 1] = childIndent .. jsonEncode(value[index], indentLevel + 1)
    end
    if #parts == 0 then
      return "[]"
    end
    return "[\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "]"
  end

  for _, key in ipairs(sortedKeys(value)) do
    parts[#parts + 1] = childIndent
      .. escapeJsonString(key)
      .. ": "
      .. jsonEncode(value[key], indentLevel + 1)
  end
  if #parts == 0 then
    return "{}"
  end
  return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
end


-- Repo-relative paths for the artifact; absolute paths would expose the local home folder.
local RELATIVE_PLUGIN_PATH = "lightroom_plugins/develop-settings-spike.lrplugin"
local RELATIVE_OUTPUT_PATH = "outputs/lightroom_sdk/lightroom_sdk_selected_develop_settings_export.json"


local function repoRoot()
  local pluginRoot = _PLUGIN.path
  return LrPathUtils.parent(LrPathUtils.parent(pluginRoot))
end


local function outputPath()
  return LrPathUtils.child(
    LrPathUtils.child(
      LrPathUtils.child(repoRoot(), "outputs"),
      "lightroom_sdk"
    ),
    "lightroom_sdk_selected_develop_settings_export.json"
  )
end


local function safeRawMetadata(photo, key)
  local ok, value = LrTasks.pcall(function()
    return photo:getRawMetadata(key)
  end)
  if ok then
    return value
  end
  return nil
end


-- fileName and copyName are formatted metadata; getRawMetadata returns nil for them.
local function safeFormattedMetadata(photo, key)
  local ok, value = LrTasks.pcall(function()
    return photo:getFormattedMetadata(key)
  end)
  if ok and value ~= "" then
    return value
  end
  return nil
end


-- The source file path is deliberately not recorded: it exposes local volume
-- and client folder names, and file_name / asset_key already identify the asset.
local function buildPhotoRecord(photo)
  local fileName = safeFormattedMetadata(photo, "fileName")

  return {
    photo_metadata = {
      asset_key = fileName and LrPathUtils.removeExtension(fileName) or nil,
      file_name = fileName,
      copy_name = safeFormattedMetadata(photo, "copyName"),
      uuid = safeRawMetadata(photo, "uuid"),
      capture_time = safeRawMetadata(photo, "dateTimeOriginal"),
    },
    develop_settings = photo:getDevelopSettings(),
  }
end


local function writeText(path, text)
  local parent = LrPathUtils.parent(path)
  LrFileUtils.createAllDirectories(parent)

  local handle, err = io.open(path, "w")
  if not handle then
    error("Could not open output file: " .. tostring(err))
  end
  handle:write(text)
  handle:write("\n")
  handle:close()
end


local function exportSelectedDevelopSettings()
  local catalog = LrApplication.activeCatalog()
  local targetPhoto = catalog:getTargetPhoto()

  if targetPhoto == nil then
    LrDialogs.message(
      "No selected target photo",
      "Select one or more photos in Lightroom, then run this plug-in again.",
      "info"
    )
    return
  end

  local selectedPhotos = catalog:getTargetPhotos()

  if selectedPhotos == nil or #selectedPhotos == 0 then
    LrDialogs.message(
      "No selected photos",
      "Select one or more photos in Lightroom, then run this plug-in again.",
      "info"
    )
    return
  end

  local records = {}
  for _, photo in ipairs(selectedPhotos) do
    records[#records + 1] = buildPhotoRecord(photo)
  end

  local exportPath = outputPath()
  local payload = {
    spike = "lightroom_sdk_selected_develop_settings_export",
    status = "complete",
    generated_at_utc = os.date("!%Y-%m-%dT%H:%M:%SZ"),
    selected_photo_count = #records,
    notes = {
      scope = "Lightroom SDK proof-of-capability spike for reading selected photo Develop settings.",
      boundary = "This artifact is written by Lightroom through the SDK. Compare it with XMP-derived Python extracts to verify whether the SDK exposes the same Develop state this repository observes externally.",
    },
    lightroom_sdk_context = {
      plugin_path = RELATIVE_PLUGIN_PATH,
      output_path = RELATIVE_OUTPUT_PATH,
    },
    records = records,
  }

  writeText(exportPath, jsonEncode(payload, 0))
  LrDialogs.message(
    "Develop settings exported",
    "Wrote " .. tostring(#records) .. " selected photo record(s) to:\n\n" .. RELATIVE_OUTPUT_PATH,
    "info"
  )
end


LrTasks.startAsyncTask(function()
  local ok, err = LrTasks.pcall(exportSelectedDevelopSettings)
  if not ok then
    LrDialogs.message(
      "Develop settings export failed",
      tostring(err),
      "critical"
    )
  end
end)
