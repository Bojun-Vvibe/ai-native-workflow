# llm-output-synapse-enable-registration-no-captcha-detector

A small detector that scans LLM-generated Matrix Synapse
configuration (typically `homeserver.yaml` and accompanying
docker-compose files) for open-registration regressions.

## Problem

Synapse refuses by default to start with `enable_registration: true`
unless one of:

- `enable_registration_captcha: true` (with valid reCAPTCHA keys),
- `registrations_require_3pid:` with at least one entry,
- `registration_requires_token: true`, or
- the explicit operator opt-out
  `enable_registration_without_verification: true`.

LLMs that try to "make signup work" routinely flip
`enable_registration: true` and add
`enable_registration_without_verification: true` to silence the
upstream safety check, producing a homeserver that anyone can
fill with throwaway accounts and use for federation / relay
abuse.

A second common failure is leaving `registration_shared_secret`
at a placeholder value (`changeme`, `secret`, `<random>`, …);
that string is a master key for the admin registration API and
must never ship as a placeholder.

## Detection logic

The detector treats the input as in scope when any Synapse marker
appears (`server_name:`, the `matrixdotorg/synapse` /
`element-hq/synapse` image, the literal `homeserver.yaml`, the
`matrix-synapse` package name, or `pid_file: /data/homeserver.pid`).

It then applies four orthogonal rules:

1. **Open registration with no guard** — `enable_registration: true`
   appears and none of `enable_registration_captcha: true`,
   `registration_requires_token: true`, or
   `registrations_require_3pid:` (with entries) is set.
2. **Verification bypass** — `enable_registration: true` appears
   alongside `enable_registration_without_verification: true` and
   no compensating guard.
3. **Captcha placeholder keys** — `enable_registration_captcha: true`
   is set but `recaptcha_public_key` / `recaptcha_private_key`
   is missing or matches a known placeholder.
4. **Shared-secret placeholder** — `registration_shared_secret`
   is one of the known placeholder values (`changeme`, `secret`,
   `password`, `replace_me`, `<random>`, empty string, …).

## False-positive notes

- The detector only fires on inputs that look like Synapse
  configuration. A `postgres` / `redis` config that happens to
  contain the literal string `enable_registration` will not
  trigger.
- A top-level comment `# synapse-registration-ok` suppresses all
  rules; use only when the homeserver is firewalled to a private
  network and the operator has explicitly accepted the risk.
- Rule 4 only flags `registration_shared_secret` when the literal
  value is a placeholder; long random strings pass.
- Captcha-key placeholders are matched case-insensitively against
  a curated list (`changeme`, `<changeme>`, `replace_me`, …).
  A genuine reCAPTCHA key (long base64-ish string) passes.

## Exit codes

- `0` — no findings.
- `N` (1..255) — number of input files that produced at least one
  finding.

## Usage

```bash
python3 detector.py path/to/homeserver.yaml [more.yaml ...]
```

## Worked example

```bash
python3 run_example.py
```

Expected:

```
summary: bad=4/4 good_false_positives=0/4
RESULT: PASS
```

## CWE references

- CWE-1188 (Insecure Default Initialization of Resource)
- CWE-307 (Improper Restriction of Excessive Authentication
  Attempts)
- CWE-693 (Protection Mechanism Failure)
