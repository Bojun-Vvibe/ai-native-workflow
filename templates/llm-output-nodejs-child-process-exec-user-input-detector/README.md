# llm-output-nodejs-child-process-exec-user-input-detector

Pure-stdlib `python3` line scanner that flags JavaScript / TypeScript
source where Node.js `child_process.exec` (or `execSync`) is invoked
with what looks like user-controlled input concatenated or
template-interpolated into the command string. This is the canonical
shell-injection footgun an LLM emits when asked to "run a shell
command with the user's argument" — `exec()` invokes `/bin/sh -c`,
so any unescaped metacharacter in the interpolated value becomes a
shell directive.

This is a **detector only**. It never executes input, never spawns
processes, and never modifies code.

## What it flags

- ``exec(`whois ${req.query.domain}`)`` — template literal
  interpolating an Express request property
- `child_process.exec("cmd " + req.body.x, cb)` — string
  concatenation with a request property
- `execSync(`ping ${process.argv[2]}`)` — argv input via template
- `exec(userInput, cb)` — bare user-input-named identifier passed
  as the command
- `exec(filename + " | tar ...")` — user input prefix-concatenated
  to a literal
- TypeScript / `.tsx` / `.mjs` / `.cjs` files using any of the above

## What it does NOT flag

- `execFile("whois", [req.query.domain])` — argv array, no shell
- `spawn("ping", ["-c", "1", host])` — argv array, no shell
- `exec("uptime", cb)` — fully literal command, no input
- Lines marked with a trailing `// child-process-exec-ok` comment
- Pattern occurrences inside `//` line comments or `/* ... */`
  block comments (single-line and multi-line)

## Layout

```
.
├── README.md                 # this file
├── detector.py               # python3 stdlib single-pass scanner
├── bad/                      # 6 fixtures that MUST be flagged
└── good/                     # 3 fixtures that MUST NOT be flagged
```

## Usage

```bash
python3 detector.py path/to/file_or_dir [more paths ...]
```

Scans `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx` files
recursively when given a directory.

Exit codes:

- `0` — no findings
- `1` — one or more findings
- `2` — usage error

## Verified output

Run from the template root:

```text
$ python3 detector.py bad/
bad/06_ts_req_params.ts:5: exec(...) with template literal interpolating user input:   exec(`tail -n 100 /var/log/${req.params.name}.log`, (err, stdout) => {
bad/01_template_req_query.js:5: exec(...) with template literal interpolating user input:   exec(`whois ${req.query.domain}`, (err, stdout) => {
bad/05_prefix_concat.js:5: exec(...) with user input prefix-concatenated to literal:   exec(filename + " | tar -czf out.tgz -", (err) => {
bad/04_bare_user_input_arg.js:5: exec(...) with user-input identifier as first argument:   exec(userInput, (err, stdout) => {
bad/02_concat_req_body.js:5: exec(...) with string concatenation of user input:   child_process.exec("mv /tmp/upload " + req.body.target, (err) => {
bad/03_execsync_argv.js:5: exec(...) with template literal interpolating user input: const out = execSync(`ping -c 1 ${target}`).toString();
$ echo $?
1

$ python3 detector.py good/
$ echo $?
0
```

All 6 bad fixtures flagged at the offending line. All 3 good
fixtures pass clean.

## Why this matters

`child_process.exec(cmd, cb)` runs `cmd` through `/bin/sh -c`. Any
shell metacharacter (`;`, `|`, `&`, `` ` ``, `$()`, newline, etc.)
in an interpolated value becomes a control character. The right
shape is `execFile(program, [arg1, arg2, ...])` or
`spawn(program, [args])` — both bypass the shell and treat the
argv array as literal arguments. LLMs frequently reach for `exec`
with a template literal because it reads more naturally to a
human; this detector keeps that reflex from landing in a pull
request.
