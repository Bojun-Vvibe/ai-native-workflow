# llm-output-tempo-multitenancy-disabled-detector

Stdlib-only Python detector that flags Grafana Tempo configurations
emitted by an LLM where multi-tenancy is silently disabled on a
deployment that is otherwise serving multiple producers/consumers.

## Why this exists

Tempo's ``multitenancy_enabled`` (and the legacy alias
``auth_enabled``) defaults to ``false``. When false, **every trace
lands in a synthetic ``single-tenant`` tenant** and the
``X-Scope-OrgID`` header from clients is ignored. LLMs commonly
copy the upstream "single-binary quickstart" verbatim into a
shared deployment, with the result that:

- traces from different teams/products co-mingle in one TSDB,
- per-tenant retention / rate-limit overrides silently no-op,
- queriers cannot enforce tenant isolation on read-back.

The detector flags four orthogonal regressions:

1. ``multitenancy_enabled: false`` (or ``no`` / ``0`` / ``off``)
   set explicitly.
2. An ``overrides:`` / ``per_tenant_override_config:`` block is
   present but multi-tenancy is not turned on (operator clearly
   expects per-tenant limits, but Tempo will not enforce them).
3. ``auth_enabled: false`` set (legacy alias — same effect).
4. A ``distributor:`` block with **two or more** receiver kinds
   (``otlp``, ``jaeger``, ``zipkin``, ``opencensus``, ``kafka``)
   and no multi-tenancy enable (deployment is clearly fan-in
   but traces will collapse into one tenant).

Suppression: a top-level ``# tempo-single-tenant-ok`` comment in
the YAML disables all rules — use only for a deliberate
single-team / lab deployment.

## API

```python
from detector import detect, scan
detect(open("tempo.yaml").read())   # bool
scan(open("tempo.yaml").read())     # [(line, reason), ...]
```

CLI:

```
python3 detector.py path/to/tempo.yaml [more.yaml ...]
```

Exit code = number of files with at least one finding.

## Layout

```
detector.py                              # rule engine (stdlib only)
test.py                                  # runs all bundled samples
examples/
  bad/
    bad_1_explicit_false.yaml            # multitenancy_enabled: false
    bad_2_auth_false_with_overrides.yaml # legacy auth_enabled: false + overrides
    bad_3_overrides_no_mt.yaml           # overrides present, MT not enabled
    bad_4_multi_receiver_no_mt.yaml      # otlp+jaeger+zipkin fan-in, no MT
  good/
    good_1_mt_true.yaml                  # multitenancy_enabled: true
    good_2_auth_true.yaml                # legacy auth_enabled: true
    good_3_minimal_lab.yaml              # single receiver, no overrides
```

## Worked example

```
$ python3 test.py
PASS bad=4/4 good=0/3
```

## Limitations

- Regex-based; assumes idiomatic YAML indentation. Heavily
  reformatted YAML or YAML embedded inside a Helm template
  ``{{ ... }}`` block may evade detection.
- Configurations split across multiple files (e.g. base + overlay)
  must be concatenated before scanning, otherwise rule 2 may
  fire on the overlay even though the base enables MT.
- Rule 4 only counts the receiver kinds that ship with
  upstream Tempo; custom receivers will not trigger fan-in
  detection.
- The detector cannot tell whether the deployment is intentionally
  single-tenant; use the ``# tempo-single-tenant-ok`` suppression
  marker for those cases.
- Local-only: no network calls, no template resolution.
