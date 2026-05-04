# llm-output-dgraph-alpha-whitelist-all-detector

Stdlib-only Python detector that flags **Dgraph `alpha`** deployments
whose `--security "whitelist=..."` value covers the public internet
(`0.0.0.0/0`, bare `0.0.0.0`, `::/0`). Maps to **CWE-284**, **CWE-732**,
**CWE-1188**, **CWE-285**, OWASP **A01:2021 Broken Access Control**.

## What it catches

Dgraph's alpha node exposes an admin GraphQL endpoint at `/admin`
that includes destructive mutations: `drop_all`, `drop_data`,
`backup`, `restore`, `shutdown`, `login`, `change password`,
`export`. Access is gated only by the `--security` flag's
`whitelist=` sub-option (and an optional `token=`).

The Dgraph getting-started tutorial uses
`--security "whitelist=0.0.0.0/0"` to make the admin endpoint
reachable from a dev laptop without setting up TLS / ACLs. LLMs
copy that quickstart line into "production" docker-compose / k8s
manifests, leaving the admin surface reachable from anywhere.

## Heuristic

Flag any `--security` (or single-dash `-security`) flag whose
`whitelist=` sub-value contains:

- `0.0.0.0/0`
- `0.0.0.0/1`
- bare `0.0.0.0` (Dgraph treats as `/0`)
- `::/0`

Do NOT flag:

- `whitelist=10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`,
  `127.0.0.0/8`, etc.
- `--security` with only `token=...` and no `whitelist=`.
- Comments / docs.

A `token=` alongside an open whitelist is **still flagged**: token
alone does not make `0.0.0.0/0` safe; admin endpoints should be
network-restricted regardless.

## Worked example

```
$ bash smoke.sh
bad=4/4 good=0/4
PASS
```

## Layout

```
examples/bad/
  01_compose_args.yaml      # docker-compose command: --security "whitelist=0.0.0.0/0"
  02_k8s_args.yaml          # k8s args: --security=whitelist=0.0.0.0/0;token=...
  03_systemd.service        # ExecStart=... -security whitelist=0.0.0.0/0
  04_dockerfile.Dockerfile  # CMD ["dgraph","alpha","--security","whitelist=::/0"]
examples/good/
  01_compose_private_cidr.yaml  # whitelist=10.0.0.0/8,192.168.0.0/16
  02_k8s_loopback.yaml          # whitelist=127.0.0.1/32
  03_token_only.service         # --security token=... (no whitelist)
  04_doc_comment_only.yaml      # bad value only inside YAML # comments
```

## Usage

```bash
python3 detect.py path/to/file
python3 detect.py path/to/repo/
```

Exit codes: `0` = clean, `1` = findings (printed to stdout), `2` =
usage error.

## Limits

- We do not parse Helm Sprig templating; values that resolve to an
  open whitelist only after rendering are out of scope.
- We do not chase environment-variable indirection
  (`DGRAPH_ALPHA_SECURITY=whitelist=0.0.0.0/0`); that form will be
  added in a follow-up if it appears in the wild.
