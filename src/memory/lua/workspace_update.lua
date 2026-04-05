--[[
Version-Checked Workspace Update (CAS Pattern)

Implements Compare-And-Swap for shared workspace updates, preventing
lost writes during concurrent multi-agent collaboration.

KEYS[1]: Workspace key (e.g., "{session:abc123}:workspace")

ARGV[1]: Expected version (int, -1 for "don't care")
ARGV[2]: New data (JSON string)
ARGV[3]: Update type ("merge" or "replace")

Returns:
    Success: New version number (int)
    Failure: -1 (version mismatch)

Version Control:
- Workspace hash contains: {data, version}
- Version increments on every successful update
- Optimistic locking prevents lost updates

Example Flow:
    1. Agent reads workspace: {data: {...}, version: 5}
    2. Agent modifies data locally
    3. Agent calls workspace_update with expected_version=5
    4. If version still 5: Update succeeds, version becomes 6
    5. If version changed: Update fails, agent must re-read and retry
]]--

local workspace_key = KEYS[1]
local expected_version = tonumber(ARGV[1])
local new_data = ARGV[2]
local update_type = ARGV[3]

-- Get current workspace state
local current_data = redis.call('HGET', workspace_key, 'data')
local current_version = tonumber(redis.call('HGET', workspace_key, 'version') or '0')

-- Check version (skip check if expected_version = -1)
if expected_version ~= -1 and current_version ~= expected_version then
    return -1  -- Version mismatch
end

-- Prepare new data based on update type
local final_data = new_data

if update_type == 'merge' and current_data then
    -- Merge operation: combine existing and new data
    local current_obj = cjson.decode(current_data)
    local new_obj = cjson.decode(new_data)
    
    -- Simple shallow merge (Python should handle deep merge)
    for k, v in pairs(new_obj) do
        current_obj[k] = v
    end
    
    final_data = cjson.encode(current_obj)
end

-- Increment version and update
local new_version = current_version + 1
redis.call('HSET', workspace_key, 'data', final_data)
redis.call('HSET', workspace_key, 'version', new_version)

-- Set TTL to 24 hours (86400 seconds)
redis.call('EXPIRE', workspace_key, 86400)

return new_version
