# llm-output-portainer-admin-password-cli-flag-detector

Stdlib-only Python detector that flags **Portainer** server
invocations which set the initial admin password via the
`--admin-password` or `--admin-password-file` CLI flag using a
plaintext / well-known value, or which expose the password value
on the command line of a long-running container (where it leaks
into `ps`, `docker inspect`, container logs, image history, and
process listings inside the container).

Maps to:
- **CWE-256**: Plaintext Storage of a Password.
- **CWE-214**: Invocation of Process Using Visible Sensitive Information.
- **CWE-798**: Use of Hard-coded Credentials (when the bcrypt hash
  is the well-known Portainer demo hash for `tryportainer`).

The Portainer docs intentionally support `--admin-password
'$2y$05$...'` (a bcrypt hash) and `--admin-password-file
/run/secrets/portainer_admin` (read at startup). The bcrypt form
is *less* dangerous than a plaintext pre-set password, but in
practice LLMs paste either:

1. `--admin-password 'admin'` / `--admin-password 'password'`
   / `--admin-password 'changeme'` — a literal plaintext (Portainer
   actually rejects non-bcrypt values, but the leak still exposes
   the intended secret to anyone with `ps` or `docker inspect`), OR
2. `--admin-password '$2y$05$qLJDZi6eY6WG.Yk7YQk6T.gKWUxhWnYI1BvhU.kHI8bkXz0lQ7Oea'`
   — the well-known bcrypt of `tryportainer` from the official
   getting-started page, which is the global default credential
   for any Portainer instance copy-pasted from those docs.

## Heuristic

We flag any of the following, outside `#` comment lines:

1. `--admin-password <value>` or `--admin-password=<value>` on a
   command line that also references `portainer` (image, binary,
   compose service name) or in a docker-compose `command:` block.
2. `--admin-password-file <path>` where `<path>` is **not** under
   `/run/secrets/`, `/var/run/secrets/`, or `/etc/portainer/secrets/`
   (i.e. the file is a regular bind-mount or baked-in path that
   defeats Docker / k8s secret rotation).
3. The well-known bcrypt hash of `tryportainer`
   (`$2y$05$qLJDZi6eY6WG.Yk7YQk6T.`) hard-coded anywhere in the
   scanned text — this is the demo credential from Portainer's
   own quickstart and is the single most common LLM paste.
4. Exec-array form: `["portainer", ..., "--admin-password", ...]`
   in k8s container args / docker-compose command arrays.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-256**: Plaintext Storage of a Password.
- **CWE-214**: Invocation of Process Using Visible Sensitive Information
  (passwords on argv leak via `/proc/<pid>/cmdline`, `docker inspect`,
  `ps auxe`, container telemetry, and crash dumps).
- **CWE-798**: Use of Hard-coded Credentials.
- Portainer docs: "For production deployments, do not use
  `--admin-password` on the command line. Use `--admin-password-file`
  pointing at a Docker secret or Kubernetes secret."

## What we accept (no false positive)

- `--admin-password-file /run/secrets/portainer_admin`
- `--admin-password-file /var/run/secrets/portainer/admin`
- Documentation / commented-out lines (`# portainer --admin-password ...`).
- Lines that mention `portainer` in unrelated contexts and do not
  also pass `--admin-password`.
- Bcrypt hashes that are not the well-known `tryportainer` demo hash.

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/docker-compose.yml
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

Every Portainer "Run in Docker" tutorial, every Helm values example,
and every k8s manifest snippet uses `--admin-password` (or the
`tryportainer` demo bcrypt hash) to skip the first-login bootstrap
prompt. LLMs asked "give me a one-liner to spin up Portainer" or
"how do I avoid the admin-init timeout" overwhelmingly suggest the
flag form. The credential then ends up in `docker inspect`, in
shell history, in CI logs, in container image labels (when the
compose file is committed), and in any orchestrator that records
container args (Nomad, k8s events, Mesos). The detector exists to
catch the paste before it gets baked into a Helm chart or a
GitOps-tracked manifest.
