# llm-output-keycloak-default-admin-detector

Static lint that flags Keycloak bootstrap configurations shipping the
well-known default admin credential `admin/admin` (or trivial variants
like `password`, `changeme`, `root`, `keycloak`) in deployable
artifacts.

Variables checked:

- Modern: `KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD`
- Quay image: `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD`
- Legacy Wildfly: `KEYCLOAK_USER` / `KEYCLOAK_PASSWORD`
- CLI flags: `--bootstrap-admin-username` / `--bootstrap-admin-password`

File shapes recognized: Dockerfile `ENV`/`ARG`, `docker-compose.yml`
`environment:`, Kubernetes manifest `env:` list (split-line
`name:`/`value:`), Secret `stringData:`, `.env` files,
shell `export` / systemd `EnvironmentFile=` lines.

## Why this matters

Keycloak's bootstrap admin is created from these environment variables
at first boot, and once the realm is committed to the database the
account persists unless an operator rotates it manually. Every
"getting started" example uses `admin/admin`, and LLM-suggested
manifests copy that verbatim into production-shaped artifacts. Because
the admin console is reachable over the same HTTPS listener as
end-user flows (`/admin`), a leaked default credential is a full
identity-provider takeover — every realm, every client, every federated
identity.

This detector is **orthogonal** to "no TLS" / "open admin console"
detectors. It only fires on the credential-strength misconfig.

## CWE references

- [CWE-798](https://cwe.mitre.org/data/definitions/798.html): Use of
  Hard-coded Credentials
- [CWE-1392](https://cwe.mitre.org/data/definitions/1392.html): Use of
  Default Credentials
- [CWE-521](https://cwe.mitre.org/data/definitions/521.html): Weak
  Password Requirements

## What it accepts

- Values that look like unresolved templating: `${...}`, `$(...)`,
  `<<TOKEN>>`, `{{ .Values.x }}`, `%ENV%`.
- Files containing the marker `# keycloak-default-admin-allowed`
  (e.g. ephemeral test fixtures).
- Non-trivial passwords (anything outside the canonical default set).

## False-positive surface

- A trivial **username** alone (e.g. `KEYCLOAK_ADMIN=admin` with the
  password sourced from a Secret) is intentionally NOT flagged —
  `admin` as the username is fine; the password is the secret.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=3/3
PASS
```

Per-finding output:

```sh
$ python3 detector.py examples/bad/01-compose.yml
examples/bad/01-compose.yml:8:KEYCLOAK_ADMIN_PASSWORD set to trivial/default value 'admin' — Keycloak bootstrap admin password must be unique per environment
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
