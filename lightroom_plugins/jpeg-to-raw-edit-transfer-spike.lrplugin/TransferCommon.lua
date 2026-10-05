local LrExportSession = import "LrExportSession"
local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"
local LrTasks = import "LrTasks"

local TransferCommon = {}

TransferCommon.spikeName = "jpeg_to_raw_edit_transfer"
TransferCommon.workingRootName = "RAW Edit Transfer"


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


local function isArray(value)
  local count = 0
  for key in pairs(value) do
    if type(key) ~= "number" then
      return false
    end
    count = count + 1
  end
  return count == #value
end


-- Objects carrying an `__order` key list are written in that order, so the
-- artifact reads summary -> context -> records. Plain maps (Develop settings
-- tables) fall back to sorted keys instead of being dropped as empty arrays.
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
    if value ~= value or value == math.huge or value == -math.huge then
      return "null"
    end
    return tostring(value)
  end
  if valueType ~= "table" then
    return escapeJsonString(value)
  end

  local indent = string.rep("  ", indentLevel)
  local childIndent = string.rep("  ", indentLevel + 1)
  local parts = {}

  if value.__order == nil and next(value) == nil then
    return "{}"
  end

  if value.__order == nil and isArray(value) then
    for index = 1, #value do
      parts[#parts + 1] = childIndent .. jsonEncode(value[index], indentLevel + 1)
    end
    return "[\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "]"
  end

  local keys = value.__order
  if keys == nil then
    keys = {}
    for key in pairs(value) do
      keys[#keys + 1] = tostring(key)
    end
    table.sort(keys)
  end
  for _, key in ipairs(keys) do
    local child = value[key]
    if child == nil and tonumber(key) ~= nil then
      child = value[tonumber(key)]
    end
    parts[#parts + 1] = childIndent
      .. escapeJsonString(key)
      .. ": "
      .. jsonEncode(child, indentLevel + 1)
  end
  return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
end

TransferCommon.jsonEncode = jsonEncode


function TransferCommon.object(order, fields)
  fields.__order = order
  return fields
end


function TransferCommon.writeJson(path, payload)
  local handle, err = io.open(path, "w")
  if not handle then
    error("Could not open output file: " .. tostring(err))
  end
  handle:write(jsonEncode(payload, 0))
  handle:write("\n")
  handle:close()
end


function TransferCommon.deepCopy(value)
  if type(value) ~= "table" then
    return value
  end
  local copy = {}
  for key, child in pairs(value) do
    copy[key] = TransferCommon.deepCopy(child)
  end
  return copy
end


function TransferCommon.deepEqual(left, right)
  if type(left) ~= type(right) then
    return false
  end
  if type(left) ~= "table" then
    return left == right
  end
  for key, child in pairs(left) do
    if not TransferCommon.deepEqual(child, right[key]) then
      return false
    end
  end
  for key in pairs(right) do
    if left[key] == nil then
      return false
    end
  end
  return true
end


-- Keys whose value differs between two settings tables, sorted.
function TransferCommon.changedKeys(before, after)
  local keys, seen = {}, {}
  for key in pairs(before) do
    seen[key] = true
  end
  for key in pairs(after) do
    seen[key] = true
  end
  for key in pairs(seen) do
    if not TransferCommon.deepEqual(before[key], after[key]) then
      keys[#keys + 1] = tostring(key)
    end
  end
  table.sort(keys)
  return keys
end


function TransferCommon.pick(settings, keys)
  local picked = {}
  for _, key in ipairs(keys) do
    picked[key] = TransferCommon.deepCopy(settings[key])
  end
  return picked
end


function TransferCommon.merge(...)
  local merged = {}
  for _, source in ipairs({ ... }) do
    for key, value in pairs(source) do
      merged[key] = TransferCommon.deepCopy(value)
    end
  end
  return merged
end


function TransferCommon.safeRawMetadata(photo, key)
  local ok, value = LrTasks.pcall(function()
    return photo:getRawMetadata(key)
  end)
  if ok then
    return value
  end
  return nil
end


-- fileName and copyName are formatted metadata; getRawMetadata returns nil for them.
function TransferCommon.safeFormattedMetadata(photo, key)
  local ok, value = LrTasks.pcall(function()
    return photo:getFormattedMetadata(key)
  end)
  if ok and value ~= "" then
    return value
  end
  return nil
end


function TransferCommon.assetKey(photo)
  local fileName = TransferCommon.safeFormattedMetadata(photo, "fileName")
  return fileName and LrPathUtils.removeExtension(fileName) or nil
end


function TransferCommon.photoIdentity(photo)
  return TransferCommon.object(
    { "asset_key", "file_format", "is_virtual_copy", "copy_name", "uuid" },
    {
      asset_key = TransferCommon.assetKey(photo),
      file_format = TransferCommon.safeRawMetadata(photo, "fileFormat"),
      is_virtual_copy = TransferCommon.safeRawMetadata(photo, "isVirtualCopy") == true,
      copy_name = TransferCommon.safeFormattedMetadata(photo, "copyName"),
      uuid = TransferCommon.safeRawMetadata(photo, "uuid"),
    }
  )
end


function TransferCommon.fileStat(path)
  local attributes = LrFileUtils.fileAttributes(path)
  if attributes == nil then
    return TransferCommon.object({ "exists" }, { exists = false })
  end
  return TransferCommon.object(
    { "exists", "size_bytes", "modified_epoch" },
    {
      exists = true,
      size_bytes = attributes.fileSize,
      modified_epoch = attributes.fileModificationDate,
    }
  )
end


-- <event>/Photo/RAW/JB*.ARW -> <event>/Photo/RAW Edit Transfer
function TransferCommon.workingRootFor(masterPath)
  local photoFolder = LrPathUtils.parent(LrPathUtils.parent(masterPath))
  return LrPathUtils.child(photoFolder, TransferCommon.workingRootName)
end


function TransferCommon.repoRoot()
  return LrPathUtils.parent(LrPathUtils.parent(_PLUGIN.path))
end


function TransferCommon.assertOutsideRepo(path)
  local repo = TransferCommon.repoRoot()
  if path:sub(1, #repo) == repo then
    error("Refusing to write private outputs inside the git checkout: " .. path)
  end
end


function TransferCommon.applySettings(catalog, photo, settings, historyName, flattenAutoNow)
  local status = catalog:withWriteAccessDo(historyName, function()
    photo:applyDevelopSettings(settings, historyName, flattenAutoNow)
  end, { timeout = 30 })
  if status ~= "executed" then
    error("Write gate not executed (" .. tostring(status) .. ") for " .. historyName)
  end
end


-- One rendition per session, so each render's file name is the variant name.
function TransferCommon.exportRender(photo, folder, fileStem, longEdge)
  local session = LrExportSession({
    photosToExport = { photo },
    exportSettings = {
      LR_export_destinationType = "specificFolder",
      LR_export_destinationPathPrefix = folder,
      LR_export_useSubfolder = false,
      LR_collisionHandling = "overwrite",
      LR_renamingTokensOn = true,
      LR_tokens = "{{custom_token}}",
      LR_tokenCustomString = fileStem,
      LR_extensionCase = "lowercase",
      LR_format = "TIFF",
      LR_export_bitDepth = 16,
      LR_tiff_compressionMethod = "compressionMethod_ZIP",
      LR_export_colorSpace = "sRGB",
      LR_size_doConstrain = true,
      LR_size_resizeType = "longEdge",
      LR_size_maxHeight = longEdge,
      LR_size_maxWidth = longEdge,
      LR_size_units = "pixels",
      LR_size_doNotEnlarge = true,
      LR_outputSharpeningOn = false,
      LR_useWatermark = false,
      LR_embeddedMetadataOption = "copyrightOnly",
      LR_removeLocationMetadata = true,
      LR_removeFaceMetadata = true,
      LR_reimportExportedPhoto = false,
    },
  })
  session:doExportOnCurrentTask()
  for _, rendition in session:renditions() do
    local ok, pathOrMessage = rendition:waitForRender()
    if not ok then
      error("Render failed for " .. fileStem .. ": " .. tostring(pathOrMessage))
    end
    return LrPathUtils.leafName(pathOrMessage)
  end
  error("No rendition produced for " .. fileStem)
end


function TransferCommon.round(value, places)
  if type(value) ~= "number" then
    return value
  end
  local scale = 10 ^ (places or 4)
  return math.floor(value * scale + 0.5) / scale
end


function TransferCommon.utcNow()
  return os.date("!%Y-%m-%dT%H:%M:%SZ")
end


return TransferCommon
