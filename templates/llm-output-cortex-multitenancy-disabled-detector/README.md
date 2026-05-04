# llm-output-cortex-multitenancy-disabled-detector

Stdlib-Python detector that flags Cortex configurations emitted by an
LLM where multi-tenancy isolation is effectively disabled.

## Why this exists

Cortex is multi-tenant by default: every read/write must be scoped by
an `X-Scope-OrgID` header. Upstream's "single-binary getting started"
doc disables auth so curl examples don't need a header. LLMs see that
shape, replicate it, and ship a deployment in which:

- every unauthenticated caller is silently bucketed into one synthetic
  tenant (`fake` by default),
- every per-tenant limit (`max_global_series_per_user`,
  `ingestion_rate`, etc.) becomes a system-wide limit,
- any reachable client can read or write any series.

The detector flags four orthogonal regressions:

1. `auth_enabled: false` at the top level of a Cortex YAML config.
2. `-auth.enabled=false` (or `--auth.enabled=false`) on a `cortex` /
   `cortex-all` CLI invocation.
3. `no_auth_tenant: <name>` set without an accompanying
   `auth_enabled: true`.
4. A Prometheus `remote_write` block targeting a Cortex
   `/api/v1/push` endpoint on a non-loopback host with no
   `X-Scope-OrgID` header.

CWE refs: CWE-862 (Missing Authorization), CWE-639 (Authorization
Bypass Through User-Controlled Key).

Suppression: a `# cortex-single-tenant-allowed` comment anywhere in
the file disables every rule (use only for local dev fixtures).

## API

```python
from detector import scan
findings = scan(open("config.yaml").read())
# findings is a list of (line_number, reason) tuples; empty == clean.
```

CLI:

```
python3 detector.py path/to/config.yaml [more.yaml ...]
```

Exit code = number of files with at least one finding.

## Layout

```
llm-output-cortex-multitenancy-disabled-detector/
  README.md
  detector.py
  run_example.py
  examples/
    bad_1_auth_enabled_false_yaml.txt
    bad_2_cli_auth_disabled.txt
    bad_3_no_auth_tenant_without_auth.txt
    bad_4_remote_write_no_xscope.txt
    good_1_auth_enabled_true.txt
    good_2_remote_write_with_xscope.txt
    good_3_suppressed_local_dev.txt
```

## Verifying

```
python3 run_example.py
```

Expected last line:

```
RESULT: PASS
```

(bad=4/4 hit, good=0/3 false-positives.)

## Scope and non-goals

- Stdlib-only; no YAML parser dependency. Regex walk over the text.
- Does not validate that a non-empty `X-Scope-OrgID` value is
  meaningful — only that *some* such header is declared in the
  `remote_write` block.
- Does not attempt to resolve indirection through env vars or Helm
  templating; treat templated configs by rendering first.
- Not a substitute for an end-to-end auth test against a running
  Cortex; it catches the static config shapes that an LLM tends to
  hand back.
