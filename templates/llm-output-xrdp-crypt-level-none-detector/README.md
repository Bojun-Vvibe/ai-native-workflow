# llm-output-xrdp-crypt-level-none-detector

Detects `xrdp.ini` configurations that downgrade the RDP wire to
`crypt_level = none` or `crypt_level = low` while still using the
legacy `security_layer = rdp` (or `negotiate` with no TLS floor).

## Why this matters

Modern xrdp ships with `security_layer = negotiate` and
`crypt_level = high`, but a long tail of online tutorials still tells
operators to set `security_layer = rdp` plus `crypt_level = none` "to
make the client connect". With those values:

- `crypt_level = none` disables RDP-level encryption entirely.
- `crypt_level = low` uses 40-bit RC4 — broken in practice for over
  two decades.
- `security_layer = rdp` skips TLS handshakes, so the on-the-wire
  bytes (including the keystrokes the user types into the desktop
  session) are recoverable with passive capture.

When `security_layer = tls` is set, xrdp requires a TLS handshake
before the inner RDP layer starts, so a low/none crypt_level is no
longer reachable — that case is treated as safe.

LLM-generated xrdp tutorials almost always emit:

    [Globals]
    security_layer=rdp
    crypt_level=none

because that is the path of least resistance to a working
`xfreerdp /v:host` from a legacy client. The detector flags that
shape so the caller can intercept it before it lands in a real
deployment.

## What it detects

For each scanned `xrdp.ini`, the detector reports a finding when, in
a `[Globals]`/`[globals]` section:

1. `crypt_level` is `none` or `low` (case-insensitive).
2. `security_layer` is `rdp` or `negotiate`.
3. `security_layer` is **not** `tls` (which would force TLS and
   render `crypt_level` moot).

The reason string also notes when `ssl_protocols` includes
deprecated `SSLv3` / `TLSv1.0`, and when no `certificate=` is
configured (so no TLS fallback is even possible).

## CWE references

- CWE-326: Inadequate Encryption Strength
- CWE-327: Use of a Broken or Risky Cryptographic Algorithm
- CWE-319: Cleartext Transmission of Sensitive Information

## False-positive surface

- `security_layer = tls` short-circuits the check; xrdp will refuse
  the legacy crypt path in that mode.
- A file that intentionally documents the legacy default (e.g. a
  hardening tutorial showing the bad config) can be suppressed with
  a comment line containing `xrdp-crypt-allowed`.

## Usage

    python3 detector.py path/to/xrdp.ini

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
