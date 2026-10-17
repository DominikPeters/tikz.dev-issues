-- Rewrite raw codeexample text, preserving the input catcodes of live pictures.
local cache = { sequence = {}, started = {} }
local begin_picture = '\\begin%s*{%s*tikzpicture%s*}'
local end_picture = '\\end%s*{%s*tikzpicture%s*}'

-- Time only the drawing body. These helpers never alter the source or output.
function cache.start(key)
    cache.started[key] = os.clock()
end

function cache.worthwhile(key, minimum_seconds)
    local started = cache.started[key]
    cache.started[key] = nil
    if started == nil then return false end
    return os.clock() - started >= minimum_seconds
end

local function exists(path)
    local stream = io.open(path, 'rb')
    if not stream then return false end
    stream:close()
    return true
end

-- Return the end of one complete outer picture, including nested pictures.
local function picture_end(source, beginning_end)
    local depth, cursor = 1, beginning_end + 1
    while depth > 0 do
        local next_begin, beginning_end = source:find(begin_picture, cursor)
        local next_end, ending_end = source:find(end_picture, cursor)
        if not next_end then return nil end
        if next_begin and next_begin < next_end then
            depth = depth + 1
            cursor = beginning_end + 1
        else
            depth = depth - 1
            cursor = ending_end + 1
        end
    end
    return cursor - 1
end

function cache.rewrite(source, id, jobname)
    assert(#id == 64 and id:match('^[a-f0-9]+$'), 'Invalid drawing cache ID')
    local parts, cursor = {}, 1
    while true do
        local start, beginning_end = source:find(begin_picture, cursor)
        if not start then break end
        local finish = picture_end(source, beginning_end)
        -- Never alter an incomplete or unfamiliar picture fragment.
        if not finish then break end
        parts[#parts + 1] = source:sub(cursor, start - 1)
        cache.sequence[id] = (cache.sequence[id] or 0) + 1
        local key = id .. '-' .. cache.sequence[id]
        local path = jobname .. '.render-cache/' .. key
        if exists(path .. '.tex') and exists(path .. '.pdf') then
            parts[#parts + 1] = '\\TikzDevCacheUse{' .. key .. '}'
        else
            parts[#parts + 1] = '\\TikzDevCacheBegin{' .. key .. '}'
                .. source:sub(start, finish) .. '\\TikzDevCacheEnd{}'
        end
        cursor = finish + 1
    end
    parts[#parts + 1] = source:sub(cursor)
    return table.concat(parts)
end

function cache.prepare(source, id, jobname)
    local rewritten = cache.rewrite(source, id, jobname)
    tex.sprint('\\expandafter\\gdef\\csname code@temp\\endcsname{')
    -- All characters are data; the manual's original scantokens reads them.
    tex.sprint(-2, rewritten)
    tex.sprint('}')
end

return cache
