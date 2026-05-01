# llm-output-bash-curl-pipe-shell-detector

Stdlib-only Python detector that flags shell scripts using the
`curl ... | sh` (or `wget ... | bash`, or any of a dozen variants)
install pattern: fetch a remote payload over the network and pipe it
straight into a shell or interpreter, with no on-disk artifact and no
integrity check.

This is the single most-recommended-against pattern in distro security
guides, but every "getting started" README still ships it, and LLMs
faithfully reproduce it.

Maps to:

- **CWE-494**: Download of Code Without Integrity Check
- **CWE-78**: OS Command Injection (when the URL contains user input)

## Why it's bad

1. The bytes you executed are never written to disk -- IR/audit
   cannot reconstruct what ran.
2. The remote can serve different content to your `curl` than to a
   verifier (User-Agent / IP-based switching).
3. A truncated download silently runs a half-script (the interpreter
   sees an unexpected EOF mid-statement, which can leave the system
   in a broken intermediate state).
4. There is no signature check, no checksum, no version pin.

## Heuristic

For each logical line (after joining `\`-continuations and skipping
`#` comments), flag the line if any of these patterns matches:

1. **Pipe form.** A `curl|wget|fetch` invocation containing an
   `http(s)://` or `ftp://` URL, followed by `|` followed by an
   interpreter from the allowlist:
   `sh, bash, zsh, ksh, dash, ash, csh, tcsh, fish, python, python3,
    python2, perl, ruby, node, php, lua` (optionally with `/usr/bin/env`).
2. **Process-substitution form.**
   `bash <(curl https://...)` and friends.
3. **Command-substitution form.**
   `sh -c "$(curl https://...)"` and friends.

## What we accept (no false positive)

- `curl -o file && sha256sum -c && bash file` — write, verify, run.
- `curl ... | jq .` — pipe target is not an interpreter.
- `cat /opt/local-installer.sh | bash` — no fetcher in the pipeline.
- The dangerous pattern appearing only inside `#` comments.
- `curl ... | tee file` — pipe target is `tee`, not a shell.

## What we flag

- `curl -fsSL https://x | bash`
- `wget -qO- https://x | sh`
- Multi-line continuation: `curl -fsSL \` then URL then `| python3`
- `bash <(curl -fsSL https://x)`
- `sh -c "$(curl -fsSL https://x)"`
- `curl -fsSL https://x | perl - --self-upgrade`

## Limits / known false negatives

- Indirect fetchers (`http`, `aria2c`, `httpie`, `xh`) are not in the
  allowlist; would need adding.
- A URL passed via a variable
  (`URL=https://x; curl "$URL" | bash`) is caught only because we
  don't resolve the variable but the `|sh` clause still matches; we
  do not currently flag the variant where the entire pipeline is
  built up via `eval`.
- Encrypted payloads piped through `openssl` or `gpg` then into a
  shell are not currently caught.

## Usage

```bash
python3 detect.py path/to/script.sh
python3 detect.py path/to/dir/   # walks *.sh, *.bash, Makefile, Dockerfile
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_curl_pipe_bash.sh                # curl ... | bash
  02_wget_pipe_sh.sh                  # wget -qO- ... | sh
  03_continuation_pipe_python.sh      # backslash continuation
  04_process_substitution.sh          # bash <(curl ...)
  05_dashc_cmdsub.sh                  # sh -c "$(curl ...)"
  06_curl_pipe_perl.sh                # curl ... | perl - args
examples/good/
  01_download_verify_run.sh           # download, sha256sum -c, then run
  02_pipe_to_jq.sh                    # pipe target is jq, not a shell
  03_local_cat_pipe_bash.sh           # no network fetcher
  04_only_in_comment.sh               # mention only in comment
  05_wget_to_file_then_run.sh         # wget to disk, then sh on file
  06_pipe_to_tee.sh                   # pipe target is tee
```
