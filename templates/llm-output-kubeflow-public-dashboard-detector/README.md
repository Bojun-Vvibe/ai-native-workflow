# llm-output-kubeflow-public-dashboard-detector

Detect Kubernetes manifests that expose the **Kubeflow central dashboard**
without authentication, by emitting an Istio `AuthorizationPolicy` whose
`action: ALLOW` is paired with an empty `rules:` list (or no `rules:` key at
all) targeting the Kubeflow namespace / dashboard workload.

Per the Istio security docs, an `ALLOW` policy with no `rules` entries
matches every request from every source — it is the policy-level equivalent
of "no auth at all". When this is the only policy guarding the
`centraldashboard` (or the `kubeflow-gateway` it sits behind), the entire
notebook / pipelines / experiments UI becomes browsable by anyone who can
reach the cluster ingress, including unauthenticated internet visitors if
the gateway is on a public LoadBalancer.

LLMs commonly emit this shape when asked things like "give me an
AuthorizationPolicy that lets the Kubeflow dashboard be reachable" — the
model interprets "be reachable" as "do not block anything" and writes the
policy without a `from:` / `when:` / `to:` restriction.

## What bad LLM output looks like

Empty rules block (literal `rules: []`):

```yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: centraldashboard-allow
  namespace: kubeflow
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: centraldashboard
  action: ALLOW
  rules: []
```

Missing `rules:` key entirely (also matches everything per Istio semantics):

```yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: kf-open
  namespace: kubeflow
spec:
  action: ALLOW
```

Rules block present but with only an empty list entry / commented entries:

```yaml
spec:
  action: ALLOW
  rules:
  # - from:
  #   - source:
  #       requestPrincipals: ["*"]
```

## What good LLM output looks like

A real `from:` clause that requires an authenticated principal:

```yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: centraldashboard-require-auth
  namespace: kubeflow
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: centraldashboard
  action: ALLOW
  rules:
    - from:
        - source:
            requestPrincipals: ["*"]
      when:
        - key: request.auth.claims[email]
          values: ["*"]
```

A `DENY` policy, or a manifest that is not for Kubeflow at all, is not
flagged. See `samples/good-3.txt` for a non-Kubeflow manifest that the
detector deliberately ignores.

## How the detector decides

1. The file must look like a Kubeflow manifest. Heuristic: it mentions
   `kubeflow` (namespace or label) **or** `centraldashboard`
   (case-insensitive).
2. The file must contain `kind: AuthorizationPolicy`.
3. Within the manifest, find the `action:` value. If it is `ALLOW`, look at
   the `rules:` block.
4. If `rules:` is missing entirely, or is `rules: []`, or contains only
   blank / commented-out entries, the file is BAD.
5. If a real rule entry exists (a `- from:` / `- to:` / `- when:` line under
   `rules:`), the file is GOOD.
6. `action: DENY` is GOOD regardless of the rules shape — DENY with empty
   rules means "deny everything", which is safe-by-default.

## Run the worked example

```sh
bash run-tests.sh
```

Expected output:

```
bad=4/4 good=0/4 PASS
```

Bad fixtures cover: literal `rules: []`, missing `rules:` key, only
commented-out entries under `rules:`, and a `kubeflow-gateway` policy with
`rules:` followed only by blank lines. Good fixtures cover: a real
authenticated `from:` clause, a `DENY` policy, a non-Kubeflow manifest the
detector should ignore, and an `AuthorizationPolicy` for a different
workload that still has a real rule entry.

## Run against your own files

```sh
bash detect.sh path/to/policy.yaml path/to/another.yaml
# or via stdin:
cat policy.yaml | bash detect.sh
```

Exit code is `0` only if every `bad-*` sample is flagged and no `good-*`
sample is flagged, so this is safe to wire into CI as a defensive
misconfiguration gate for Kubeflow deployments.
