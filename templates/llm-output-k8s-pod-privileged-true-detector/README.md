# llm-output-k8s-pod-privileged-true-detector

Stdlib-only Python detector that flags **Kubernetes** workload
manifests (Pod / Deployment / StatefulSet / DaemonSet / Job / CronJob /
ReplicaSet / ReplicationController) with at least one container set
to `securityContext.privileged: true`.

A privileged container shares the host's kernel capabilities, devices,
and namespaces — it can mount any host filesystem, load kernel
modules, and trivially escape the cluster boundary. This is the
single highest-leverage misconfiguration LLMs introduce when a user
pastes a `permission denied` log and asks the model to "fix it so it
runs."

## Why this exact shape

`privileged: true` is the only Pod-spec key that, on its own, fully
disables the container sandbox. It's distinct from finer-grained
escalations (`hostNetwork`, `hostPID`, `CAP_SYS_ADMIN`, etc.) — those
deserve their own detectors. Catching the literal first gives the
highest-precision, lowest-noise check we can write without a YAML
parser.

## Heuristic

1. The file must contain a top-level `kind:` matching one of the
   workload kinds above. This eliminates random non-k8s YAML
   (CI configs, Compose files, Ansible vars).
2. At least one line matches `^\s*privileged\s*:\s*(true|True|yes|on)`
   (with optional trailing comment). The leading-whitespace anchor
   means a `privileged: true` token appearing inside a quoted string
   or trailing comment will not trip the detector.

We don't use a YAML parser — adding a runtime YAML dep contradicts
the "stdlib only" rule. The path:line we emit makes manual
verification trivial.

## CWE / standards

- **CWE-250**: Execution with Unnecessary Privileges.
- **CIS Kubernetes Benchmark 5.2.1**: Minimize the admission of
  privileged containers.
- **NIST SP 800-190 §4.4.4**: Container runtime security.
- **Pod Security Standards**: privileged containers are forbidden
  under both `baseline` and `restricted` profiles.

## Limits / known false negatives

- We don't follow `$()` Helm/Kustomize templating. A manifest where
  `privileged: {{ .Values.allowPrivileged }}` defaults to `true` will
  not trip until rendered.
- Multi-document YAML with the offending container in a doc that has
  no `kind:` line of its own (rare) won't trip if no other doc in the
  same file declares one of the recognized kinds.
- We don't flag `hostPID: true`, `hostNetwork: true`,
  `allowPrivilegeEscalation: true`, or `CAP_SYS_ADMIN` — those each
  warrant their own detector.

## Usage

```bash
python3 detect.py path/to/manifest.yaml
python3 detect.py path/to/dir/   # walks *.yaml and *.yml
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

### Worked example — `python3 detect.py examples/bad/`

```
$ python3 detect.py examples/bad/
examples/bad/06_cronjob_backup.yaml:16: container running with privileged=true (CWE-250 / CIS K8s 5.2.1): privileged: true   # so we can mount the host data dir
examples/bad/05_statefulset_cache.yaml:18: container running with privileged=true (CWE-250 / CIS K8s 5.2.1): privileged: true
examples/bad/02_deployment_web.yaml:18: container running with privileged=true (CWE-250 / CIS K8s 5.2.1): privileged: true
examples/bad/01_pod_debug.yaml:11: container running with privileged=true (CWE-250 / CIS K8s 5.2.1): privileged: true
examples/bad/04_job_migrate.yaml:13: container running with privileged=true (CWE-250 / CIS K8s 5.2.1): privileged: True
examples/bad/03_daemonset_agent.yaml:17: container running with privileged=true (CWE-250 / CIS K8s 5.2.1): privileged: true
$ echo $?
1
```

### Worked example — `python3 detect.py examples/good/`

```
$ python3 detect.py examples/good/
$ echo $?
0
```

Layout:

```
examples/bad/
  01_pod_debug.yaml             # bare Pod with privileged: true
  02_deployment_web.yaml        # Deployment, web container privileged
  03_daemonset_agent.yaml       # DaemonSet + hostNetwork + privileged
  04_job_migrate.yaml           # Job, value spelled `True`
  05_statefulset_cache.yaml     # StatefulSet, privileged + escalation
  06_cronjob_backup.yaml        # CronJob with trailing comment
examples/good/
  01_pod_explicit_false.yaml    # privileged: false
  02_deployment_hardened.yaml   # drops ALL caps, no privileged key
  03_daemonset_caps_only.yaml   # adds one capability, not privileged
  04_job_safe.yaml              # runAsNonRoot, no privileged key
  05_statefulset_hardened.yaml  # readOnlyRootFilesystem etc.
  06_cronjob_with_comment.yaml  # comment mentions phrase, not key
```
