# llm-output-sshd-permitemptypasswords-yes-detector

## Problem

The OpenSSH `sshd_config` directive `PermitEmptyPasswords` controls whether
the server will allow login to accounts whose password field is empty. The
default is `no` and the manpage is blunt:

> PermitEmptyPasswords
>   When password authentication is allowed, it specifies whether the server
>   allows login to accounts with empty password strings.  The default is no.

When an LLM scaffolds a "minimal sshd config to get into the box quickly," it
sometimes emits `PermitEmptyPasswords yes`. Combined with the typical sibling
default of `PasswordAuthentication yes`, this lets any account with a blank
password (often `root` on a freshly-imaged dev box, or service accounts
created by `useradd -m foo` without `passwd`) accept any password — including
the empty string.

This is a one-liner, pattern-matchable misconfig that should never reach a
running host.

## Why a detector

LLM-emitted sshd snippets in tutorials, Dockerfiles (`echo "PermitEmptyPasswords
yes" >> /etc/ssh/sshd_config`), Ansible tasks, and cloud-init `write_files`
blocks all share the same shape. A small, deterministic regex catches every
form before the config is shipped.

## Detection rule

Flag any line where, after stripping leading whitespace and inline `#`
comments, the directive is `PermitEmptyPasswords` (case-insensitive — sshd
itself parses keywords case-insensitively) and the value token is `yes` (also
case-insensitive).

The detector also scans:
- Plain `*.conf` / `sshd_config` / `*.txt` files line-by-line.
- Fenced markdown blocks tagged `sshd_config`, `sshd`, `ssh`, or `conf`.
- `Dockerfile`-style `RUN echo "PermitEmptyPasswords yes" >> ...` and
  `RUN sed -i 's/.*PermitEmptyPasswords.*/PermitEmptyPasswords yes/' ...`
  shapes — by stripping common shell wrappers (`echo`, quotes, `>>`,
  `tee`, `printf`) and re-tokenising.

## Usage

```
python3 detector.py path/to/sshd_config [more ...]
```

Exit code is the count of files with at least one finding. Findings print as
`path:line: <line>` to stdout.

Run the bundled fixtures:

```
./test.sh
```

Expected: `4/4` bad fixtures flag, `0/3` good fixtures flag, exit 0.

## Limitations

- Does not follow `Include` directives.
- Does not understand `Match` blocks — a `PermitEmptyPasswords yes` inside a
  `Match User backup` block is flagged regardless. That is intentional.
- A line like `# PermitEmptyPasswords yes` (the manpage example, commented
  out) is correctly ignored.
