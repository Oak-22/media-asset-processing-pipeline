local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"
local LrTasks = import "LrTasks"

local SpikeCommon = {}

SpikeCommon.spikeName = "crop_auto_vs_upright_level"


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


-- Objects are written in the order given by their `__order` key list, so the
-- artifact reads summary -> context -> records rather than alphabetically.
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

  local indent = string.rep("  ", indentLevel)
  local childIndent = string.rep("  ", indentLevel + 1)
  local parts = {}

  if value.__order == nil then
    for index = 1, #value do
      parts[#parts + 1] = childIndent .. jsonEncode(value[index], indentLevel + 1)
    end
    if #parts == 0 then
      return "[]"
    end
    return "[\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "]"
  end

  for _, key in ipairs(value.__order) do
    parts[#parts + 1] = childIndent
      .. escapeJsonString(key)
      .. ": "
      .. jsonEncode(value[key], indentLevel + 1)
  end
  return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
end


function SpikeCommon.object(order, fields)
  fields.__order = order
  return fields
end


local function repoRoot()
  return LrPathUtils.parent(LrPathUtils.parent(_PLUGIN.path))
end


SpikeCommon.outputDir = "outputs/lightroom_sdk"


function SpikeCommon.writeArtifact(fileName, payload)
  local directory = LrPathUtils.child(
    LrPathUtils.child(repoRoot(), "outputs"),
    "lightroom_sdk"
  )
  LrFileUtils.createAllDirectories(directory)
  local path = LrPathUtils.child(directory, fileName)

  local handle, err = io.open(path, "w")
  if not handle then
    error("Could not open output file: " .. tostring(err))
  end
  handle:write(jsonEncode(payload, 0))
  handle:write("\n")
  handle:close()
  return SpikeCommon.outputDir .. "/" .. fileName
end


function SpikeCommon.safeRawMetadata(photo, key)
  local ok, value = LrTasks.pcall(function()
    return photo:getRawMetadata(key)
  end)
  if ok then
    return value
  end
  return nil
end


function SpikeCommon.photoIdentity(photo)
  local fileName = SpikeCommon.safeRawMetadata(photo, "fileName")
  return {
    asset_key = fileName and LrPathUtils.removeExtension(fileName) or nil,
    file_name = fileName,
    copy_name = SpikeCommon.safeRawMetadata(photo, "copyName"),
    uuid = SpikeCommon.safeRawMetadata(photo, "uuid"),
  }
end


-- Upright's Level correction (UprightTransform_3) is stored as a row-major 3x3
-- similarity in normalized image coordinates:
--   [ s*cos, -s*sin*H/W, tx ; s*sin*W/H, s*cos, ty ; 0, 0, 1 ]
-- Returns its rotation in degrees, or nil when no Level analysis is stored.
function SpikeCommon.levelRotationDegrees(settings)
  local matrix = settings and settings.UprightTransform_3
  if type(matrix) ~= "string" then
    return nil
  end
  local values = {}
  for number in matrix:gmatch("[^,]+") do
    values[#values + 1] = tonumber(number)
  end
  if #values ~= 9 then
    return nil
  end
  local a, b, c = values[1], values[2], values[4]
  local sine = math.sqrt(math.abs(b * c))
  if c < 0 then
    sine = -sine
  end
  return math.deg(math.atan2(sine, a))
end


function SpikeCommon.round(value, places)
  if value == nil then
    return nil
  end
  local scale = 10 ^ (places or 4)
  return math.floor(value * scale + 0.5) / scale
end


function SpikeCommon.utcNow()
  return os.date("!%Y-%m-%dT%H:%M:%SZ")
end


return SpikeCommon
