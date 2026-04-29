# Bad fixture: each line below should produce a finding.

import os, strutils

# 1: classic staticExec on a concatenated string
const sha = staticExec("git rev-parse HEAD")

# 2: gorge — alias of staticExec, equally dangerous
const branch = gorge("git symbolic-ref --short HEAD")

# 3: gorgeEx — staticExec with stdin and stderr
const out = gorgeEx("sh", input = "echo hello", cache = "x")

# 4: staticRead pulling an arbitrary build-host file at compile time
const secrets = staticRead("/etc/hostname")

# 5: pragma form — {.compile: ...} with a templated path
{.compile: "vendor/" & "shim.c".}

# 6: pragma {.passC: ...} taking a build-time string
{.passC: "-DBUILD_TAG=" & sha.}

# 7: pragma {.passL: ...}
{.passL: "-L/opt/lib -lthing".}

# 8: triple-quoted argument — call site still flags
const banner = staticExec("""printf 'still dynamic\n'""")

echo sha, " ", branch, " ", out, " ", secrets, " ", banner
