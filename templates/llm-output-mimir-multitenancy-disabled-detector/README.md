# llm-output-mimir-multitenancy-disabled-detector

Stdlib-Python detector that flags Grafana Mimir / Loki / Tempo /
Cortex configs emitted by an LLM where multi-tenancy is disabled
(`auth_enabled: false` or `multitenancy_enabled: false`) on a
deployment exposed beyond loopback.

## Why this exists

Upstream's "getting started" YAML for Mimir/Loki/Tempo all set
`auth_enabled: false`. That collapses every incoming request onto a
hard-coded `fake` tenant and removes the `X-Scope-OrgID` requirement.
LLMs replicate the getting-started shape verbatim, then push it into
helm values that expose the gateway via `LoadBalancer`/`NodePort`. At
that point any reachable client can read or overwrite any other
tenant's series.

The detector flags four orthogonal regressions:

1. Top-level `auth_enabled: false` / `multitenancy_enabled: false`
   in a YAML that has Mimir/Loki/Tempo/Cortex context.
2. Nested helm values, e.g.
   `mimir.structuredConfig.auth_enabled: false`.
3. CLI invocation: `-auth.multitenancy-enabled=false` while
   `-server.http-listen-address` resolves to a non-loopback bind
   (or is omitted, which defaults to 0.0.0.0).
4. Same key at any indent inside a values file with product context.

CWE refs: CWE-862 (Missing Authorization), CWE-639 (Authorization
Bypass Through User-Controlled Key — when multitenancy is enabled
without a gateway enforcing `X-Scope-OrgID`, the header is a
self-asserted tenant claim).

Suppression: a top-level `# multitenancy-disabled-allowed` comment
in the first 5 lines, or a per-line trailing
`# multitenancy-disabled-allowed`. Use only for local dev fixtures
bound to loopback.

## API

```python
from detector import scan
findings = scan(open("mimir.yaml").read())
```

CLI:

```
python3 detector.py mimir.yaml [more.yaml ...]
```

## Layout

```
detector.py
run_example.py
examples/
  bad_1_mimir_multitenancy_off.txt
  bad_2_loki_auth_off.txt
  bad_3_helm_structured.txt
  bad_4_cli_args.txt
  good_1_multitenancy_on.txt
  good_2_loopback_with_suppression.txt
  good_3_cli_multitenancy_on.txt
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_mimir_multitenancy_off.txt: FLAG (1 finding(s))
    L2: multitenancy_enabled=false disables tenant isolation; all requests collapse onto the 'fake' tenant
  bad_2_loki_auth_off.txt: FLAG (1 finding(s))
    L2: auth_enabled=false disables tenant isolation; all requests collapse onto the 'fake' tenant
  bad_3_helm_structured.txt: FLAG (1 finding(s))
    L4: auth_enabled=false disables tenant isolation; all requests collapse onto the 'fake' tenant
  bad_4_cli_args.txt: FLAG (1 finding(s))
    L3: -auth.multitenancy-enabled=false while http listener bound to 0.0.0.0 (non-loopback) — see line 4

== good samples (should each produce 0 findings) ==
  good_1_multitenancy_on.txt: ok (0 finding(s))
  good_2_loopback_with_suppression.txt: ok (0 finding(s))
  good_3_cli_multitenancy_on.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/3
RESULT: PASS
```

## Limitations

- Regex-based; the detector requires product context keywords
  (`mimir`, `loki`, `tempo`, `cortex`, etc.) to fire on the YAML rule
  and avoid false positives on unrelated `auth_enabled: false` keys
  in other ecosystems.
- The CLI rule does not expand env-var substitution; render args
  before scanning if your runtime injects them at exec time.
- This is local static analysis only; it does not check Ingress/L7
  auth, mTLS, or the actual `X-Scope-OrgID` enforcement at the
  gateway. Pair with an integration test for that.
