# llm-output-vector-api-no-auth-detector

Stdlib-Python detector that flags Vector (the observability data
pipeline) configs emitted by an LLM where the management/GraphQL API
is bound to a non-loopback host.

## Why this exists

Vector ships an HTTP+GraphQL API behind `[api]`. The API has **no
built-in authentication and no built-in authorization**. Anyone who
can reach the bound address can:

- read every component's full config and runtime metrics,
- subscribe over GraphQL to the live event stream flowing through the
  pipeline (which routinely carries logs that contain secrets),
- load the GraphQL `playground` UI when `playground = true` and
  explore the schema interactively.

Upstream's "enable the API" snippet uses `address = "0.0.0.0:8686"`
to make it reachable from a host browser. LLMs replicate that snippet
verbatim and ship it to production deployments where the port is
published, exposing a zero-auth introspection plane.

The detector flags four orthogonal regressions:

1. TOML `[api]` table with `enabled = true` and `address` bound to a
   non-loopback host.
2. YAML `api:` block with `enabled: true` and a non-loopback
   `address`.
3. `playground = true` while the address is non-loopback (the
   playground should never be reachable off-host).
4. CLI / docker invocation with `--api-address <non-loopback>`.

CWE refs: CWE-306 (Missing Authentication for Critical Function),
CWE-732 (Incorrect Permission Assignment for Critical Resource).

Suppression: a `# vector-api-public-allowed` comment anywhere in the
file disables every rule (use only for local dev fixtures).

## API

```python
from detector import scan
findings = scan(open("vector.toml").read())
# findings is a list of (line_number, reason) tuples; empty == clean.
```

CLI:

```
python3 detector.py path/to/vector.toml [more.yaml ...]
```

Exit code = number of files with at least one finding.

## Layout

```
llm-output-vector-api-no-auth-detector/
  README.md
  detector.py
  run_example.py
  examples/
    bad_1_toml_zero_zero.txt
    bad_2_yaml_with_playground.txt
    bad_3_cli_api_address.txt
    bad_4_ipv6_unspec_with_playground.txt
    good_1_loopback_only.txt
    good_2_api_disabled.txt
    good_3_suppressed_dev_fixture.txt
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

- Stdlib-only; regex walk over the text. No TOML or YAML parser.
- Treats default address (when `enabled=true` but no `address` set)
  as safe — Vector's own default is `127.0.0.1:8686`.
- Does not detect that an external auth proxy in front of Vector
  would mitigate the exposure; the file-local view is what an LLM
  hands back, so we judge it locally.
- Not a substitute for a network-policy audit; catches the static
  config shapes an LLM tends to emit.
