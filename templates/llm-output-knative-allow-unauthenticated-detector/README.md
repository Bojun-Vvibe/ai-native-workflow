# llm-output-knative-allow-unauthenticated-detector

Flags Knative Serving manifests / install scripts that allow
unauthenticated invocation of a Knative service -- the value used
in nearly every Knative quickstart, and the one operators forget
to remove before exposing a cluster to the public internet.

## What it detects

All gated by an in-file Knative context token (`knative`,
`serving.knative.dev`, `kservice`, `ksvc`, `run.googleapis.com`,
`cloud-run`):

1. RBAC `(Cluster)RoleBinding` whose `subjects:` include
   `kind: Group` / `name: system:unauthenticated` AND whose
   `roleRef:` points at a `serving.knative.dev` role.
2. `gcloud run deploy ... --allow-unauthenticated` (Cloud Run for
   Anthos / Knative-on-GKE managed flavour).
3. `gcloud run services add-iam-policy-binding --member=allUsers`
   (or `allAuthenticatedUsers`) granting `run.invoker`.
4. `kubectl create (cluster)rolebinding --group=system:unauthenticated`
   in a Knative-aware install script.

## Why this is dangerous

Knative serves user code over HTTP. If invocation is open to
`system:unauthenticated` / `allUsers`:

- the entire public internet can invoke the service without any
  credential -- think "your AI inference endpoint billed per
  call" or "your internal admin dashboard";
- attackers can probe for SSRF / RCE in the workload itself
  without first having to compromise a token;
- per-request egress / data-exfil channels open up from inside
  the cluster network;
- per-invocation cost (GPU, autoscaler cold-starts, downstream
  API quota) is now attacker-controlled.

## CWE / OWASP refs

- **CWE-862**: Missing Authorization
- **CWE-284**: Improper Access Control
- **CWE-732**: Incorrect Permission Assignment for Critical Resource
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A01:2021** -- Broken Access Control

## False positives

Skipped:

- Files with no Knative context token (an unrelated RBAC binding
  that grants `system:unauthenticated` access to a non-Knative
  resource is out of scope here -- a different detector should
  cover that).
- Comment-only mentions of `--allow-unauthenticated` in docs.
- `gcloud run deploy ... --no-allow-unauthenticated` (the
  explicit *secure* form).

## Run

```
python3 detect.py path/to/file-or-dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```
$ ./smoke.sh
bad=4/4 good=0/3
PASS
```

Four `examples/bad/` files (RBAC `ClusterRoleBinding` YAML,
`gcloud-deploy.sh` with `--allow-unauthenticated`, `add-iam.sh`
binding `allUsers`, `kubectl-bind.sh` with
`--group=system:unauthenticated`) each trip the detector. Three
`examples/good/` files (a Knative `RoleBinding` bound only to a
named `ServiceAccount`, a `--no-allow-unauthenticated` deploy
script, and an IAM binding restricted to a named user) all stay
clean.
