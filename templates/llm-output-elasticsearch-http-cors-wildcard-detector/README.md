# llm-output-elasticsearch-http-cors-wildcard-detector

Static lint that flags `elasticsearch.yml` files where HTTP CORS is
enabled with a wildcard origin allow-list.

Elasticsearch's HTTP layer ships CORS disabled by default. When an
operator enables it (`http.cors.enabled: true`) and pairs that with
`http.cors.allow-origin: "*"` (or the regex equivalent `/.*/`), any
origin in any browser tab can issue authenticated cross-origin
requests against the cluster's HTTP API. If
`http.cors.allow-credentials: true` is also set, browser cookies and
HTTP auth headers are attached, turning a single visit to a hostile
page into a full read/write of the cluster (CWE-942 / CWE-346).

LLM-generated `elasticsearch.yml` files routinely emit:

```yaml
http.cors.enabled: true
http.cors.allow-origin: "*"
http.cors.allow-credentials: true
```

or:

```yaml
http.cors.enabled: true
http.cors.allow-origin: /.*/
```

This detector parses each YAML key/value (both flat dotted form and
nested form) and flags any file where `http.cors.enabled` is true
and `http.cors.allow-origin` is a wildcard (`*` or `/.*/`).

## What it catches

- `http.cors.enabled: true` paired with `http.cors.allow-origin: "*"`.
- The regex wildcard form `/.*/` (with or without quotes).
- Both flat dotted form and nested YAML form.
- `http.cors.allow-credentials: true` is reported as an escalation.

## CWE references

- [CWE-942](https://cwe.mitre.org/data/definitions/942.html):
  Permissive Cross-domain Policy with Untrusted Domains
- [CWE-346](https://cwe.mitre.org/data/definitions/346.html):
  Origin Validation Error
- [CWE-352](https://cwe.mitre.org/data/definitions/352.html):
  Cross-Site Request Forgery (downstream impact)

## False-positive surface

- Files containing `# es-cors-wildcard-allowed` are skipped wholesale
  (use for committed dev-only fixtures).
- Files with `http.cors.enabled: false` (or unset) are not flagged
  even if `allow-origin` is wildcarded — the CORS layer is dormant.
- Concrete origin values (`https://kibana.internal`) are not flagged.
- Files with no `http.cors.*` keys at all are not flagged.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `smoke.sh` — alias for `run.sh`, kept for harness symmetry.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
