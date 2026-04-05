--[[
Smart Append with Automatic Windowing and TTL

Atomically appends data to a list with automatic size limiting and TTL
refresh. Used for L1 turn storage with sliding window behavior.

KEYS[1]: List key (e.g., "{session:abc123}:turns")

ARGV[1]: Data to append (JSON string)
ARGV[2]: Window size (int, max list length)
ARGV[3]: TTL in seconds (int, e.g., 86400 for 24 hours)

Returns:
    New list length after append (int)

Operations (atomic):
    1. LPUSH data to list (prepend to head)
    2. LTRIM to keep only recent window_size entries
    3. EXPIRE to refresh TTL

Example:
    Key: "{session:abc123}:turns"
    Window: 20
    TTL: 86400 (24 hours)
    
    Result: List always contains ≤20 most recent turns, auto-expires if
    no activity for 24 hours.

Performance:
    Single Lua call vs 3 separate commands eliminates network round-trips
    and race conditions.
]]--

local list_key = KEYS[1]
local data = ARGV[1]
local window_size = tonumber(ARGV[2])
local ttl_seconds = tonumber(ARGV[3])

-- Append to head of list
local new_length = redis.call('LPUSH', list_key, data)

-- Trim to window size (keep 0 to window_size-1)
redis.call('LTRIM', list_key, 0, window_size - 1)

-- Refresh TTL
redis.call('EXPIRE', list_key, ttl_seconds)

-- Return actual length after trim
local final_length = redis.call('LLEN', list_key)
return final_length
