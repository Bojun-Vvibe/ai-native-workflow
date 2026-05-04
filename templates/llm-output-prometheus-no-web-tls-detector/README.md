# llm-output-prometheus-no-web-tls-detector

Stdlib-only Python detector that flags Prometheus deployments
emitted by an LLM where the HTTP server is bound to a non-loopback
interface but no ``--web.config.file`` (the upstream knob for TLS
and basic-auth) is configured.

## Why this exists

Since Prometheus 2.24 the binary ships native TLS + basic-auth
support via ``--web.config.file=/path/web.yml``. The upstream docs
state this is the supported gate for the HTTP API. LLMs commonly
produce one of these unsafe shapes:

1. ``--web.listen-address=0.0.0.0:9090`` (or ``:9090``) with **no**
   ``--web.config.file=`` flag at all — the API, the metrics, the
   target list, and (when enabled) the lifecycle/admin endpoints
   are reachable from anywhere with no gate.
2. ``--web.enable-admin-api`` enabled together with a public
   listen-address and no ``--web.config.file`` — the admin API
   can wipe TSDB and create snapshots.
3. ``--web.enable-lifecycle`` enabled together with a public
   listen-address and no ``--web.config.file`` — the lifecycle
   API can reload config or shut the server down.
4. A ``web.yml`` referenced by ``--web.config.file=`` that
   contains an empty ``tls_server_config: {}`` and an empty
   ``basic_auth_users: {}`` — file present, but neither gate is
   actually configured.

The detector recognises the equivalent shapes inside docker-compose
``command:`` arrays, k8s ``args:``, systemd ``ExecStart=``, and raw
shell snippets. Loopback / localhost binds are treated as safe
(the listener is not reachable from the network).

Suppression: a top-level ``# prometheus-public-readonly-ok``
comment in the file disables all rules (intentional public mirror).

## API

```python
from detector import detect, scan
detect(open("compose.yml").read())   # -> bool
scan(open("compose.yml").read())     # -> [(line, reason), ...]
```

CLI:

```
python3 detector.py path/to/compose.yml [more.yaml ...]
```

Exit code = number of files with at least one finding.

## Layout

```
detector.py
test.py
examples/
  bad/
    bad_1_compose_no_webconfig.yaml      # 0.0.0.0:9090, no web.config.file
    bad_2_k8s_admin_api.yaml             # admin API + public bind
    bad_3_systemd_lifecycle.service      # lifecycle API + public bind
    bad_4_webconfig_empty.yaml           # web.yml with empty TLS + empty basic_auth
  good/
    good_1_compose_webconfig.yaml        # public bind WITH --web.config.file
    good_2_loopback_only.service         # 127.0.0.1 bind, no gate needed
    good_3_webconfig_full.yaml           # web.yml with real TLS + bcrypt user
```

## Worked example

```
$ python3 test.py
PASS bad=4/4 good=0/3
```

## Limitations

- Regex-based; assumes the binary flags are written verbatim
  (compose ``command:`` array, k8s ``args:``, systemd
  ``ExecStart=``, shell). Wrappers that translate some other
  config format into the final flags must be rendered first.
- The detector does NOT check the *contents* of the file
  pointed at by ``--web.config.file`` unless that content is
  embedded in the same scan blob as rule 4. To cover the
  separate-file case, scan the web-config file directly as a
  second invocation.
- Rule 4 fires only when **both** ``tls_server_config`` and
  ``basic_auth_users`` are empty. A file that configures one
  but not the other is treated as intentional (TLS-only or
  basic-auth-only deployments are valid).
- Comment lines starting with ``#`` are stripped before
  matching to avoid false positives from documentation strings;
  ``#`` inside a quoted YAML value is preserved.
- Local-only: no network calls, no template resolution.
