# llm-output-kubernetes-privileged-pod-detector

Flag Kubernetes manifests where a container's `securityContext` sets
`privileged: true`.

## Why

A privileged container effectively runs as root on the node. The
container is granted all Linux capabilities, the AppArmor / SELinux
default profile is disabled, and `/dev` from the host is exposed to
the container. From a privileged pod an attacker can:

- Mount the host filesystem and read or modify any file on the node.
- Load kernel modules, write to `/proc/sys/...`, change cgroup
  limits, and reach the container runtime socket.
- Trivially escape the container using well-known techniques
  (release_agent, core_pattern, mounting `/dev/sda1`, etc.).

This maps to:

- **CWE-250** — Execution with Unnecessary Privileges.
- **CWE-269** — Improper Privilege Management.
- **CIS Kubernetes Benchmark 5.2.1** — Minimize the admission of
  privileged containers.
- **NSA/CISA Kubernetes Hardening Guidance** — pod security.

LLMs reach for `privileged: true` as a one-line "fix" when a user
pastes a permission-denied error from inside a container, because it
makes the immediate symptom disappear without forcing the model to
reason about the actual capability or mount that was missing.

## What this flags

Any workload manifest where a line matches:

    privileged: true

(or `True`, `yes`, `on`) and the document declares `kind:` of one of:

- `Pod`
- `Deployment`
- `StatefulSet`
- `DaemonSet`
- `Job`
- `CronJob`
- `ReplicaSet`
- `ReplicationController`
- `PodTemplate`

A per-line suppression marker is supported:

    privileged: true  # llm-allow:privileged-pod

## What this does NOT flag

- `privileged: false` (explicit safe value).
- The field appearing in a comment-only line or unrelated YAML
  (no recognized workload `kind:` in the same file).
- The related but distinct fields `allowPrivilegeEscalation`,
  `runAsUser: 0`, `capabilities.add: [SYS_ADMIN]`, or `hostPID`.
  Those are separate hazards and warrant separate detectors.
- Pod Security Admission policy YAML that *describes* the
  `privileged` profile name as a string — the matched line must be
  the boolean field, not a string value like `enforce: privileged`.

## Usage

    python3 detect.py <file_or_dir> [...]

Recurses into directories looking for `*.yaml` and `*.yml`. Exit
code is `1` if any findings, `0` otherwise. Stdlib only.

## Verify

    bash verify.sh

Expected output: `bad=4/4 good=3/3` summary line, then `PASS`.
