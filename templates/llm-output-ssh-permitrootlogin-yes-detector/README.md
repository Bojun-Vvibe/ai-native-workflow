# llm-output-ssh-permitrootlogin-yes-detector

Flag OpenSSH server config (`sshd_config`) where `PermitRootLogin`
is set to `yes`.

## Why

`PermitRootLogin yes` allows direct interactive SSH login as `root`
with a password. Consequences:

- Brute-force and credential-stuffing attacks against `root` have a
  one-step path to full system compromise — no privilege escalation,
  no `sudo` log entry, no second factor by default.
- Audit trails lose attribution: every action is performed as `root`,
  with no record of which human operator initiated the session.
- Configuration management, intrusion detection, and many compliance
  baselines (CIS, STIG, PCI-DSS) explicitly forbid it.

The OpenSSH project's own default has been `prohibit-password`
(formerly `without-password`) since OpenSSH 7.0 (2015). Setting it
back to `yes` is almost always a regression introduced to "fix"
a login error, not a deliberate hardening choice.

This maps to:

- **CWE-250** — Execution with Unnecessary Privileges.
- **CWE-1188** — Insecure Default Initialization of Resource.
- **CIS Distribution Independent Linux Benchmark** — control
  "Ensure SSH root login is disabled".

LLMs reach for `PermitRootLogin yes` as a one-line fix when a user
pastes "Permission denied (publickey)" or "root login refused", even
though the correct fix is almost always to use a non-root user with
`sudo`, or to set `prohibit-password` and supply an SSH key.

## What this flags

In any file whose name is `sshd_config`, ends in `.sshd_config`,
ends in `_sshd_config`, lives under a directory named `sshd_config.d`,
or is given explicitly on the command line, lines matching:

    PermitRootLogin yes

Matching is case-insensitive on the directive name (OpenSSH itself
is case-insensitive on directive names), tolerates leading whitespace,
tolerates a trailing comment, and matches the value `yes` only.

A per-line suppression marker is supported:

    PermitRootLogin yes  # llm-allow:sshd-permitrootlogin

## What this does NOT flag

- `PermitRootLogin no`
- `PermitRootLogin prohibit-password` (the modern OpenSSH default)
- `PermitRootLogin without-password` (the older spelling of the same)
- `PermitRootLogin forced-commands-only`
- A line that is entirely a comment (`# PermitRootLogin yes`).
- The directive appearing inside a `Match` block — the directive is
  flagged regardless of block context. (Limiting `PermitRootLogin
  yes` to a `Match` block does not make it safe; it just narrows
  the scope.)

## Usage

    python3 detect.py <file_or_dir> [...]

When given a directory, recurses and inspects files whose basename
is `sshd_config` or that live under a `sshd_config.d` directory.
Exit code is `1` if any findings, `0` otherwise. Stdlib only.

## Verify

    bash verify.sh

Expected output: `bad=4/4 good=4/4` summary line, then `PASS`.
