# llm-output-n8n-basic-auth-disabled-detector

Stdlib-Python detector that flags n8n self-hosted deployment
configs emitted by an LLM where the editor / REST API is left
without authentication.

## Why this exists

n8n is a workflow-automation server that holds long-lived OAuth
tokens, API keys, SMTP credentials, and database DSNs for every
connected service. Self-hosted deployments are gated by HTTP basic
auth (``N8N_BASIC_AUTH_USER`` / ``N8N_BASIC_AUTH_PASSWORD``) only
when ``N8N_BASIC_AUTH_ACTIVE=true``. The default is **false** —
LLMs that copy the upstream "minimal" docker-compose verbatim ship
a fully-open editor, and anyone who can reach the port gets an
authenticated session against every connected workflow.

The detector flags four orthogonal regressions:

1. ``N8N_BASIC_AUTH_ACTIVE=false`` (or any falsy synonym).
2. ``N8N_BASIC_AUTH_ACTIVE`` absent entirely while the deployment
   is exposed beyond localhost (``N8N_HOST`` set to a non-loopback
   value, or ``N8N_TUNNEL=true``).
3. ``N8N_BASIC_AUTH_ACTIVE=true`` with ``N8N_BASIC_AUTH_PASSWORD``
   empty or missing (n8n still accepts the empty credential).
4. ``N8N_BASIC_AUTH_ACTIVE=true`` with a well-known default
   password literal (``changeme``, ``password``, ``admin``,
   ``n8n``, ``secret``, ``123456``, any case).

Truthy synonyms (``true`` / ``yes`` / ``1`` / ``on``, any case) are
all treated as enabled. Files that do not mention any ``N8N_*``
key are out of scope.

CWE refs: CWE-306 (Missing Authentication for Critical Function),
CWE-1188 (Insecure Default Initialization of Resource).

Suppression: a top-level ``# n8n-basic-auth-disabled-ok`` comment
in the file disables all rules (use only for an isolated lab
deployment that is firewalled off the public internet).

## API

```python
from detector import scan
findings = scan(open("docker-compose.yml").read())
# findings is a list of (line_number, reason) tuples; empty == clean.
```

CLI:

```
python3 detector.py path/to/compose.yml [more.env ...]
```

Exit code = number of files with at least one finding.

## Layout

```
detector.py                              # the rule engine (stdlib only)
run_example.py                           # worked example, runs all bundled samples
examples/
  bad_1_active_false.txt                 # N8N_BASIC_AUTH_ACTIVE=false on a public host
  bad_2_active_absent_public.txt         # N8N_HOST set, BASIC_AUTH_ACTIVE never declared
  bad_3_password_empty.txt               # active=true but password is ""
  bad_4_default_password.txt             # active=true with password "changeme"
  good_1_active_true_strong_password.txt # auth on, strong password
  good_2_localhost_only.txt              # bound to loopback, auth off
  good_3_unrelated_env.txt               # no n8n keys at all
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_active_false.txt: FLAG (1 finding(s))
    L14: N8N_BASIC_AUTH_ACTIVE=false (editor and REST API exposed without authentication; long-lived workflow credentials reachable to anyone who can connect)
  bad_2_active_absent_public.txt: FLAG (1 finding(s))
    L5: N8N_BASIC_AUTH_ACTIVE not set while n8n is exposed beyond localhost (default is false; editor and REST API are reachable without auth)
  bad_3_password_empty.txt: FLAG (1 finding(s))
    L7: N8N_BASIC_AUTH_PASSWORD is empty while N8N_BASIC_AUTH_ACTIVE=true (empty password is accepted)
  bad_4_default_password.txt: FLAG (1 finding(s))
    L12: N8N_BASIC_AUTH_PASSWORD is a well-known default ('changeme'); rotate before exposing the editor

== good samples (should each produce 0 findings) ==
  good_1_active_true_strong_password.txt: ok (0 finding(s))
  good_2_localhost_only.txt: ok (0 finding(s))
  good_3_unrelated_env.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/3
RESULT: PASS
```

## Limitations

- Regex-based; assumes env-var-style consumption (compose, k8s
  ConfigMap, systemd EnvironmentFile, raw shell). Wrappers that
  translate a different key name into ``N8N_BASIC_AUTH_*`` need to
  render the final env first.
- The detector does not understand alternative front-end auth
  layers (forward-auth via Traefik / nginx / oauth2-proxy). If
  external auth is enforced, suppress the file with the comment
  marker.
- Configs that split auth and host across multiple files (e.g. one
  ConfigMap + one Secret) must be concatenated before scanning,
  otherwise rule 2 will fire.
- The detector is local-only: it does not resolve template values,
  pull secrets, or talk to the daemon.
