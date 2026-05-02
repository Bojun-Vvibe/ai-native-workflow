# llm-output-grafana-allow-embedding-detector

Static lint that flags Grafana `grafana.ini` / `custom.ini` files where
`allow_embedding = true` is set in the `[security]` section, disabling
Grafana's default frame-busting / clickjacking defenses.

Grafana ships with `allow_embedding = false` by default. When set to
`true`, Grafana drops the `X-Frame-Options: DENY` header (and the
`frame-ancestors` CSP) from its responses, so any external site can
embed Grafana panels in an `<iframe>`. Combined with cookie-based
session auth, this enables clickjacking attacks against Grafana
admins (e.g. an attacker site frames Grafana, overlays a transparent
button, and tricks the admin into clicking "Delete data source" or
"Add admin user").

LLM-generated configs frequently set this to `true` to "support
embedding panels in our portal" without considering that the same flag
also lets *every other origin* embed Grafana.

## What it catches

- `allow_embedding = true` (case-insensitive, with or without spaces
  around `=`, with or without quotes, with `# ...` / `; ...` trailing
  comments) inside the `[security]` section.
- Truthy variants: `true`, `1`, `yes`, `on`.
- Same key set at the very top (no section header yet) is flagged
  too, since Grafana's ini parser treats it as a security key.
- Combined with `cookie_samesite = none` → flagged with an extra
  "cross-site cookie" finding.

## CWE references

- [CWE-1021](https://cwe.mitre.org/data/definitions/1021.html):
  Improper Restriction of Rendered UI Layers or Frames (Clickjacking)
- [CWE-693](https://cwe.mitre.org/data/definitions/693.html):
  Protection Mechanism Failure
- [CWE-1275](https://cwe.mitre.org/data/definitions/1275.html):
  Sensitive Cookie with Improper SameSite Attribute (when paired with
  `cookie_samesite = none`)

## False-positive surface

- Embedding Grafana panels into a trusted internal portal that is
  served on the same origin / behind the same SSO. Suppress per file
  with a comment `# grafana-embedding-allowed` (or `; ...`) anywhere
  in the file.
- `allow_embedding = false` (the default) is treated as safe.
- Same key under a non-`[security]` section is treated as inert
  (Grafana ignores it).

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
