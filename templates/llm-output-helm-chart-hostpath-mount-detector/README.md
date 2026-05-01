# llm-output-helm-chart-hostpath-mount-detector

Stdlib-only Python detector that flags **Helm chart templates** (and
plain Kubernetes manifests) which mount a node path into a Pod via
`hostPath`. Maps to **CWE-732: Incorrect Permission Assignment for
Critical Resource**: a hostPath volume punches through the pod-host
isolation boundary and gives the workload direct access to the
underlying node's filesystem.

Mounting paths like `/`, `/etc`, `/var/run/docker.sock`, `/var/lib/kubelet`,
`/proc`, or `/sys` is effectively a node-takeover primitive: a compromised
container can read kubelet credentials, talk to the container runtime
socket, or write to host init scripts.

LLMs reach for `hostPath` because it is the shortest way to "share state
with the node" or "scrape host logs". Helm-charted manifests slip past
review because the dangerous bit is buried inside `values.yaml`-driven
indentation.

## Heuristic

For each line in a YAML/TPL file we walk:

1. **Inline form** — `hostPath: { path: /etc }` → flag.
2. **Block form** — `hostPath:` followed (within ≤12 indented lines) by
   `path: <value>` → flag.
3. **Bare** — `hostPath:` with no resolvable child path → still flag
   (the surface itself is the hazard).

Helm-templated values like `path: {{ .Values.hostDir }}` are treated as
**SENSITIVE**: an LLM author can wire any path through `values.yaml`
later, so we cannot prove the chart is safe.

Sensitive-path prefixes that are flagged loudly:
`/`, `/etc`, `/var/run/docker.sock`, `/var/run`, `/var/lib/kubelet`,
`/var/lib/docker`, `/proc`, `/sys`, `/root`, `/home`, `/dev`.

## CWE / standards

- **CWE-732**: Incorrect Permission Assignment for Critical Resource.
- **CWE-250**: Execution with Unnecessary Privileges.
- **CIS Kubernetes Benchmark §5.7.x** — Minimize the admission of containers wishing to share the host.
- **NSA/CISA Kubernetes Hardening Guidance** — Avoid hostPath volumes.

## What we accept (no false positive)

- `emptyDir: {}` — pod-local scratch.
- `configMap:` / `secret:` / `projected:` / `persistentVolumeClaim:` — supported volume sources.
- `# hostPath: /etc` inside a comment.
- Files that do not contain a `hostPath` key.

## What we flag

- Block-form `hostPath:` with `path: /etc`.
- Inline `hostPath: { path: /var/run/docker.sock }`.
- Helm-templated `path: {{ .Values.hostDir }}` (treated SENSITIVE).
- Bare `hostPath:` mapping with no resolved path (still hazard surface).
- Multi-document streams separated by `---`.

## Limits / known false negatives

- We do not render Helm templates first; chart logic that *conditionally*
  inserts `hostPath` based on `if .Values.enableHostMount` is flagged
  whenever the textual occurrence exists, which is intentional (the
  capability is the risk).
- We do not flag `hostNetwork: true`, `hostPID: true`, `hostIPC: true`
  — those have separate detectors in this series.
- We do not parse `values.yaml` to resolve interpolations.

## Usage

```bash
python3 detect.py path/to/chart/templates/
python3 detect.py path/to/manifest.yaml
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_root_mount.yaml             # hostPath: /
  02_docker_sock.yaml            # /var/run/docker.sock
  03_kubelet_dir.yaml            # /var/lib/kubelet
  04_inline_form.yaml            # hostPath: { path: /etc }
  05_helm_templated_path.yaml    # path: {{ .Values.hostDir }}
  06_proc_mount.yaml             # /proc
examples/good/
  01_emptydir.yaml               # emptyDir: {}
  02_configmap_volume.yaml       # configMap volume
  03_pvc_volume.yaml             # persistentVolumeClaim
  04_secret_volume.yaml          # secret volume
  05_comment_only.yaml           # `# hostPath:` in comment
  06_no_volumes.yaml             # Pod with no volumes at all
```
