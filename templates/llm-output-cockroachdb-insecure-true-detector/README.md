# llm-output-cockroachdb-insecure-true-detector

Stdlib-only Python detector that flags **CockroachDB** invocations
which start the node in insecure mode (`--insecure`). Maps to
**CWE-319** (cleartext transmission of sensitive information),
**CWE-306** (missing authentication for critical function), and
**CWE-1188** (insecure default initialization of resource).

`cockroach start --insecure` (and `cockroach start-single-node
--insecure`, and `cockroach demo --insecure`) tells CockroachDB to:

- skip TLS for both inter-node and SQL client connections,
- skip password authentication for the `root` user,
- skip certificate validation entirely.

The CockroachDB docs are explicit: *"An insecure cluster exposes
absolutely everyone to the data, and is not recommended for any
production environment."* Yet `--insecure` is the single most common
copy-paste from getting-started tutorials, demo videos, and LLM
answers to "why does cockroach refuse to start without certs?".

## Heuristic

We flag any of the following, outside `#` comment lines:

1. `--insecure` flag passed to `cockroach start`, `cockroach
   start-single-node`, or `cockroach demo` on a shell command line
   (Dockerfile CMD/ENTRYPOINT, shell wrapper, systemd `ExecStart`,
   k8s args).
2. Exec-array form: `["cockroach", "start", ..., "--insecure"]`
   or `["cockroach", "start-single-node", ..., "--insecure"]`
   in k8s container args / docker-compose `command:` arrays.
3. Env-var override `COCKROACH_INSECURE=true` (read by `cockroach
   sql` and the recent server entrypoints in the official image).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-319**: Cleartext Transmission of Sensitive Information.
- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- CockroachDB docs (`cockroach start`): "Start a node with no
  encryption or authentication. Intended for non-production testing
  only. **Do not use this flag for any production deployment.**"

## What we accept (no false positive)

- `cockroach start --certs-dir=...` (the secure-mode invocation).
- `cockroach sql --insecure` against a *separate* dev cluster — note
  we still flag it; the detector is intentionally strict about any
  `--insecure` on a `cockroach` line, and the README documents this
  so reviewers can suppress with a `# noqa: insecure-mode` comment
  if they truly mean it. (A future relaxation could limit to
  `start*` subcommands; this version errs on the side of catching.)
- Documentation / commented-out lines (`# cockroach start --insecure`).
- Words that share the substring `insecure` but are not the flag
  (e.g. `insecure_mode_audit_log`, `# this is insecure: …`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/Dockerfile
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

The CockroachDB quickstart, every "Run Cockroach in Docker" blog
post, and every k8s demo manifest uses `--insecure` because it
eliminates the cert-management chapter from the tutorial. LLMs
therefore overwhelmingly suggest `--insecure` when asked to
"give me a docker-compose for cockroach" or "fix `ERROR: problem
using security settings`". The flag is one token, gets reviewed as
trivial, and ships into staging clusters that very quickly become
prod clusters. The detector exists to catch the paste before it
gets baked into a Helm chart.
