# llm-output-kubernetes-host-network-true-detector

Flag Kubernetes manifests where a workload sets `hostNetwork: true`
on the Pod spec.

## Why

`hostNetwork: true` puts the pod into the host's network namespace.
Consequences:

- The pod can bind on host ports, including privileged ports.
- The pod can reach localhost-only services on the node — kubelet's
  read-only port, etcd peer/client ports if co-located, the cloud
  metadata service (`169.254.169.254`), node-local DNS caches, the
  Docker socket if exposed on a UNIX or TCP port.
- NetworkPolicy is bypassed: NetworkPolicy operates on the pod's own
  network namespace, which the pod no longer has.
- A compromise of the container becomes a compromise of the node's
  network identity.

This maps to:

- **CWE-668** — Exposure of Resource to Wrong Sphere.
- **CIS Kubernetes Benchmark 5.2.4** — Minimize the admission of
  containers wishing to share the host network namespace.
- **NSA/CISA Kubernetes Hardening Guidance** — pod isolation.

LLMs reach for `hostNetwork: true` as the fastest way to silence
"connection refused on 127.0.0.1" or "permission denied binding port
80" when a user pastes an error and asks for a quick fix.

## What this flags

Any workload manifest where a line matches:

    hostNetwork: true

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

    hostNetwork: true  # llm-allow:host-network

## What this does NOT flag

- `hostNetwork: false` (explicit safe value).
- The field appearing only in a comment or string literal — we
  require a matching `kind:` workload declaration in the same file.
- YAML that doesn't look like a Kubernetes workload (no recognized
  `kind:`).
- The related but distinct fields `hostPID`, `hostIPC`, `hostPort`,
  `hostAliases`. These are separate hazards that warrant separate
  detectors.

## Usage

    python3 detect.py <file_or_dir> [...]

Recurses into directories looking for `*.yaml` and `*.yml`. Exit
code is `1` if any findings, `0` otherwise. Stdlib only.

## Verify

    bash verify.sh

Expected output: `bad=6/6 good=6/6` summary line, then `PASS`.
