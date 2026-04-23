# Probe checklist (per leaf command)

For each leaf command of the CLI, walk through this checklist and
record the answers. This produces the raw material for the
behavior spec. Aim for ~10 minutes per leaf command after you have
the rhythm.

Replace `<cmd>` with the command under test (e.g. `the-cli sync`).

## Pass 1 — Surface

- [ ] `<cmd> --help` exit code: ___, output captured: ___
- [ ] `<cmd> -h` exit code: ___, output differs from `--help`? ___
- [ ] All flags listed: ___
- [ ] Hidden flags found via `strings` / `--debug` discovery: ___
- [ ] Required positional args: ___
- [ ] Optional positional args: ___
- [ ] Default values for each optional flag: ___

## Pass 2 — Output shape (happy path)

- [ ] Representative input used: ___
- [ ] stdout content: ___
- [ ] stdout format: text / json / tsv / mixed: ___
- [ ] stderr content (should be empty on success): ___
- [ ] Exit code on success: ___
- [ ] Files created: ___
- [ ] Files modified: ___
- [ ] Files deleted: ___
- [ ] Network calls made (capture with `tcpdump` / proxy if needed): ___
- [ ] Deterministic output? If not, which fields vary: ___
- [ ] Effect of `--json` / `--format=json` on stdout (if supported): ___
- [ ] Effect of `--quiet` / `--verbose` (if supported): ___

## Pass 3 — Failure modes

For each, record exit code + stderr message + any side effects:

- [ ] No arguments at all: ___
- [ ] Missing required positional: ___
- [ ] Missing required flag: ___
- [ ] Wrong type for a flag (e.g. string where int expected): ___
- [ ] Nonexistent input path: ___
- [ ] Unreadable input path (permissions): ___
- [ ] Nonexistent output path: ___
- [ ] Read-only output path: ___
- [ ] Disk full (simulate with small tmpfs if relevant): ___
- [ ] Network unreachable (if CLI does network): ___
- [ ] Invalid auth / expired token (if CLI does auth): ___
- [ ] Rate-limited (if CLI does network): ___
- [ ] Concurrent invocation on same target: ___
- [ ] SIGINT mid-operation — leaves partial state? ___
- [ ] SIGTERM mid-operation — leaves partial state? ___

## Pass 4 — Configuration & environment

- [ ] Strace / dtruss `open()` log captured: ___
- [ ] Config files read (in order tried): ___
- [ ] Config file format: ___
- [ ] Required config fields: ___
- [ ] Optional config fields + defaults: ___
- [ ] Environment variables read (from binary strings + observed): ___
- [ ] Precedence when env + flag both set: ___
- [ ] Precedence when config + env both set: ___
- [ ] State / cache directory: ___
- [ ] State / cache file format: ___
- [ ] Does the CLI ever write to `$HOME` outside its config dir? ___

## Pass 5 — Notes for the spec

- [ ] Surprising behaviors worth a "Quirks" entry: ___
- [ ] Things I tested but couldn't fully determine: ___
- [ ] Things I deliberately did NOT test (and why): ___
- [ ] CLI version probed: ___
- [ ] Date probed: ___
- [ ] Probe environment (OS, shell, locale): ___
