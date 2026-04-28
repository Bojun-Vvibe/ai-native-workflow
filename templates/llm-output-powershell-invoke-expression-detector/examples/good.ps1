# Good fixture: zero findings expected.
# Demonstrates the safe alternatives to Invoke-Expression / iex.

$cmd = "Get-Process"

# Call operator with a known cmdlet — preferred over Invoke-Expression:
& Get-Process

# Scriptblock invocation with literal body:
& { Get-Date; Get-Location }

# Building an argument list and invoking via a known cmdlet:
$argList = @("-Force", "prod")
Start-Process -FilePath "deploy.exe" -ArgumentList $argList

# Invoke-Command is a different cmdlet (remote execution) — NOT flagged.
# Invoke-WebRequest / Invoke-RestMethod are also different — NOT flagged.
Invoke-WebRequest "https://example.test/data.json" -OutFile data.json
Invoke-RestMethod "https://example.test/api"

# Functions named Invoke-ExpressionLogger or iex_helper should NOT match:
function Invoke-ExpressionLogger { param($s) Write-Host "would-iex: $s" }
Invoke-ExpressionLogger "Get-Date"

function iex_helper { param($s) Write-Host "wrapped: $s" }
iex_helper "Get-Date"

# Variables named $iex_log should NOT match:
$iex_log = "trace"
Write-Host $iex_log

# Strings/comments mentioning Invoke-Expression should NOT trigger:
$msg = "Do not call Invoke-Expression `$cmd in production"
Write-Host $msg
# This comment mentions Invoke-Expression $cmd as an anti-pattern, also fine.

# Suppression marker on an audited line:
$audited = "Get-Date"
Invoke-Expression $audited  # iex-ok: reviewed 2026-04-29, sandboxed test harness
