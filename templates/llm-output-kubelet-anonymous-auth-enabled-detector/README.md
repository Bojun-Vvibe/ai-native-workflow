# llm-output-kubelet-anonymous-auth-enabled-detector

Detect kubelet configurations that LLMs commonly emit with anonymous
authentication enabled on the kubelet's HTTPS API (port `10250`) or its
legacy read-only HTTP API (port `10255`). Anonymous access to either
endpoint is a documented lateral-movement primitive: an attacker who can
reach the node can list pods, read container logs, and (when paired
with permissive authorization) `exec` into containers — all with no
credentials. The CIS Kubernetes Benchmark §4.2.1 and the NSA/CISA
Kubernetes Hardening Guide both call this out.

The hardening knobs that close this off are:

- `KubeletConfiguration` YAML: `authentication.anonymous.enabled: false`
  AND `readOnlyPort: 0` (or omitted; the typed schema defaults the
  read-only port to disabled).
- CLI flags: `--anonymous-auth=false`, `--read-only-port=0`.
- A `--config <file>` pointer that supplies the above.

When asked "give me a kubelet config" or "set up a single-node
Kubernetes cluster", LLMs routinely emit a working unit file that
either flips `anonymous.enabled` to `true`, sets
`readOnlyPort: 10255` "for Prometheus", or starts the bare binary with
no `--config` and no `--anonymous-auth=false` (the binary's compiled-in
default for a flagless start is anonymous-on).

This detector is orthogonal to the kube-apiserver / etcd / controller-
manager hardening detectors: it targets the *node-agent* tier, which
each cluster has many of, and which is reachable from any pod that can
talk to the node IP.

Related weaknesses: CWE-306 (Missing Authentication for Critical
Function), CWE-284 (Improper Access Control), CWE-668 (Exposure of
Resource to Wrong Sphere).

## What bad LLM output looks like

Anonymous explicitly enabled in the typed config:

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
authentication:
  anonymous:
    enabled: true
authorization:
  mode: AlwaysAllow
```

Read-only port re-opened "for metrics scraping":

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
authentication:
  anonymous:
    enabled: false
readOnlyPort: 10255
```

CLI flag overriding the config file:

```
--anonymous-auth=true --authorization-mode=AlwaysAllow
```

Bare-binary start with no `--config` and no `--anonymous-auth=false`:

```sh
exec /usr/bin/kubelet \
  --hostname-override=node-01 \
  --container-runtime-endpoint=unix:///run/containerd/containerd.sock
```

## What good LLM output looks like

- A `KubeletConfiguration` with `anonymous.enabled: false` AND
  `readOnlyPort: 0` (or omitted).
- A CLI invocation with `--anonymous-auth=false` AND
  `--read-only-port=0`.
- An invocation that points `--config` at an external file the
  detector cannot inspect (we defer to the file-based rules).

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/kubelet_config_anonymous_true.yaml
BAD  samples/bad/kubelet_config_read_only_port.yaml
BAD  samples/bad/start_kubelet_no_config.sh
BAD  samples/bad/systemd_kubelet_anonymous_true.conf
GOOD samples/good/kubelet_config_anonymous_false.yaml
GOOD samples/good/kubelet_config_no_anonymous_block.yaml
GOOD samples/good/start_kubelet_with_config.sh
GOOD samples/good/systemd_kubelet_anonymous_false.conf
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good
samples are flagged.

## Detector rules

A file is classified into exactly one of two modes; the YAML mode wins
when both YAML markers and a `kubelet` invocation appear in the same
file:

1. **`KubeletConfiguration` YAML** (contains `kind: KubeletConfiguration`
   or `apiVersion: kubelet.config.k8s.io/...`). Flagged if either:
   - The `authentication.anonymous.enabled` field is `true`. The check
     is indentation-aware (a hand-rolled awk pass) so a stray top-level
     `enabled: true` outside the `anonymous:` block does not match.
   - `readOnlyPort:` is set to a non-zero integer.
2. **Pure invocation** (`kubelet` on the command line, no embedded
   `KubeletConfiguration`). Flagged if any of:
   - `--anonymous-auth=true` (or `--anonymous-auth true`).
   - `--read-only-port=<non-zero>` (or `--read-only-port <non-zero>`).
   - Neither `--anonymous-auth=false` nor `--config <file>` is present
     (the bare-binary default is unsafe).

`#` line comments and inline `# ...` tails are stripped before
matching. The flag normalizer drops `"`, `,`, `[`, `]` so JSON-array
`CMD ["kubelet","--anonymous-auth=true"]` and `Environment="..."`
forms both match.

## Known false-positive notes

- A YAML that declares `authentication.anonymous: {}` (no `enabled:`
  child) will not be flagged; the typed schema defaults the field to
  `false`. This matches kubeadm's generated configs.
- A YAML with a stray `enabled: true` under an unrelated block (e.g.,
  `webhook: { enabled: true }`) will not match thanks to the
  indentation-aware walker.
- Multi-document YAML files (`---` separators) are scanned as a single
  stream; if any document in the stream contains an enabled anonymous
  block, the whole file is flagged. This is consistent with how
  `kubectl apply -f` would treat the file.
- An invocation with `--config` pointing at a file the detector cannot
  see is treated as safe-by-deferral; pair this detector with whatever
  process you use to vet the referenced config.
