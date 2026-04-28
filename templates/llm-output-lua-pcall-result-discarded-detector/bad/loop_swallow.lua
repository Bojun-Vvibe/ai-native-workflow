-- Bad: result discarded inside a loop — the model "added error
-- handling" by wrapping each iteration in pcall but never reads it.
local M = {}

function M.run_all(jobs)
    for i = 1, #jobs do
        pcall(jobs[i])
    end
end

-- Bonus: comments and strings mentioning pcall(foo) must NOT trigger.
-- e.g. "we previously called pcall(foo) here" and the string below:
local doc = "see README: pcall(http.get, url) is now wrapped"

return M
