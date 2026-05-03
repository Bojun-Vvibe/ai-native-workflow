# llm-output-gerrit-auth-type-development-become-any-account-detector

Static lint that flags Gerrit `gerrit.config` files (and Gerrit
launch commands) where the `[auth]` `type` is set to
`DEVELOPMENT_BECOME_ANY_ACCOUNT`.

Gerrit's `DEVELOPMENT_BECOME_ANY_ACCOUNT` auth type is documented
strictly as a **local development convenience**: it lets any
anonymous visitor "become" any registered account — including the
admin account — by clicking through the "Become" page, with no
credential check. Shipping that value in a network-reachable
`etc/gerrit.config` is a complete authentication bypass
(CWE-287: Improper Authentication, CWE-1188: Insecure Default
Initialization of Resource, CWE-306: Missing Authentication for
Critical Function).

LLM-generated bootstrap configs and Dockerfile `CMD` lines often
emit this value verbatim because it is the simplest auth setting
in every "first run" tutorial:

```ini
[auth]
    type = DEVELOPMENT_BECOME_ANY_ACCOUNT
[gerrit]
    canonicalWebUrl = http://gerrit.example.com/
```

```Dockerfile
CMD ["java", "-jar", "/var/gerrit/bin/gerrit.war", "daemon", \
     "-c", "auth.type=DEVELOPMENT_BECOME_ANY_ACCOUNT"]
```

## What it catches

- Any file named `gerrit.config` whose `[auth]` section sets
  `type = DEVELOPMENT_BECOME_ANY_ACCOUNT` on an active
  (non-comment) line.
- Any shell script / Dockerfile / systemd unit file that launches
  Gerrit with `-c auth.type=DEVELOPMENT_BECOME_ANY_ACCOUNT` or
  `--config auth.type=DEVELOPMENT_BECOME_ANY_ACCOUNT` (line must
  also mention `gerrit` / `GerritCodeReview` to keep false
  positives down).
- Inline comments (`;` and `#`) are stripped from values; quoted
  values are unwrapped.

## CWE references

- [CWE-287](https://cwe.mitre.org/data/definitions/287.html):
  Improper Authentication
- [CWE-1188](https://cwe.mitre.org/data/definitions/1188.html):
  Insecure Default Initialization of Resource
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html):
  Missing Authentication for Critical Function

## False-positive surface

- Files containing `# gerrit-development-auth-allowed` (or `;`
  variant) are skipped wholesale (use for local-only smoke
  fixtures).
- Any other `auth.type` value (`OAUTH`, `LDAP`, `HTTP`,
  `OPENID`, `CUSTOM_EXTENSION`, etc.) is accepted.
- Comment lines starting with `#` or `;` are ignored.
- The CLI form requires the source file to mention `gerrit` /
  `GerritCodeReview` somewhere so unrelated `auth.type=...`
  strings in generic config tooling don't trip.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at
  least one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `smoke.sh` — alias for `run.sh`, kept for harness symmetry.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
