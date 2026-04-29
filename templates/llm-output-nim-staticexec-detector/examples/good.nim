# Good fixture: zero findings expected.

import os, strutils

# 1: a string literal that mentions staticExec — masked, not flagged
let warn = "do not use staticExec(userInput) in build scripts"
echo warn

# 2: a comment that mentions gorge("git rev-parse HEAD") — masked
# (no actual call here)

# 3: triple-quoted documentation containing pragma syntax — masked
let doc = """
The {.compile: "x.c".} pragma is dangerous when the path is templated.
"""
echo doc

# 4: read the build sha via -d:buildSha=... from the command line — safe
const buildSha {.strdefine.} = "unknown"
echo "build: ", buildSha

# 5: an explicit dispatch table for compile-time choices — safe
const flavor {.strdefine.} = "release"
const flavorFlag = case flavor
  of "release": "-O3"
  of "debug":   "-O0"
  else:         "-O2"
echo "flavor flag: ", flavorFlag

# 6: a proc literally named `staticReader` — not flagged (whole-word match)
proc staticReader(p: string): string = "stub:" & p
echo staticReader("ignored")

# 7: an audited staticExec line, suppressed explicitly
const date = staticExec("date -u +%Y%m%d")  # nim-static-ok — fixed argv, audited
echo date

# 8: raw-string literal that happens to contain "gorge(...)" — masked
let raw = r"gorge(""ignored"")"
echo raw
