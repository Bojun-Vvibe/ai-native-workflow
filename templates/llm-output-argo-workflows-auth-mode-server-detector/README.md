# llm-output-argo-workflows-auth-mode-server-detector

Detect Argo Workflows server deployments that LLMs commonly emit with
the `server` auth mode enabled and no other auth mode alongside it.
The `server` mode tells the Argo Workflows API server to act with the
identity of its own ServiceAccount for every incoming request, so any
unauthenticated caller who can reach the API endpoint inherits the
server's RBAC — typically cluster-wide workflow create / submit / pod
exec rights. The Argo Workflows docs explicitly warn that `server`
mode is "convenient for local development" and "should not be used
alone in shared or production clusters", but LLMs routinely paste it
into Helm values, Deployment manifests, and `argo server` invocations
when asked "give me an Argo Workflows quickstart".

The hardening knobs that close this off are:

- Use `--auth-mode=client` (the default) and let the UI / CLI pass a
  bearer token, OR
- Use `--auth-mode=sso` with an OIDC provider, OR
- Pass `--auth-mode=client,sso` (multiple modes are allowed; `server`
  must not be the *only* mode).

When asked "deploy Argo Workflows" or "expose the Argo UI", LLMs
commonly emit a Deployment / Helm values fragment / `argo server`
command line that sets `auth.mode: [server]` or
`--auth-mode=server` as the sole mode, on the rationale that "this
makes the UI work without logging in". It does — for the attacker
too.

This detector is orthogonal to the argocd-admin-default-password
detector (Argo CD ≠ Argo Workflows; different product, different auth
surface) and to the kubelet / kube-apiserver detectors (those target
the cluster control plane, not a workflow-engine API server running
inside it).

Related weaknesses: CWE-306 (Missing Authentication for Critical
Function), CWE-285 (Improper Authorization), CWE-269 (Improper
Privilege Management).

## What bad LLM output looks like

`server` as the sole auth mode in a Helm values fragment:

```yaml
server:
  extraArgs:
    - --auth-mode=server
```

`server` as the sole entry of a list-form `auth.mode`:

```yaml
auth:
  mode:
    - server
```

A `Deployment` whose container args contain only `--auth-mode=server`:

```yaml
spec:
  containers:
    - name: argo-server
      image: quay.io/argoproj/argocli:v3.5.1
      args: ["server", "--auth-mode=server"]
```

A bare `argo server` invocation with the same flag:

```sh
argo server --auth-mode=server --namespaced=false
```

## What good LLM output looks like

- `--auth-mode=client` (the default).
- `--auth-mode=sso` with an OIDC provider configured.
- `--auth-mode=client,sso` or a YAML list `[client, sso]` (multiple
  modes are supported and `server` is absent).
- An invocation that omits `--auth-mode` entirely (the binary's
  default is `client`).

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/argo_server_cli.sh
BAD  samples/bad/deployment_args_server_only.yaml
BAD  samples/bad/helm_values_extra_args.yaml
BAD  samples/bad/helm_values_mode_list.yaml
GOOD samples/good/argo_server_client_mode.sh
GOOD samples/good/deployment_args_client_sso.yaml
GOOD samples/good/helm_values_mode_client_sso.yaml
GOOD samples/good/helm_values_no_auth_mode.yaml
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero
good samples are flagged.

## Detector rules

A file is flagged iff at least one of the following is true after
`#`-comment stripping:

1. **CLI flag form**: a token that matches
   `--auth-mode=server` (or `--auth-mode server`, with or without
   surrounding quotes / commas / brackets) appears AND no other
   `--auth-mode=...` token sets a non-`server` value in the same file.
2. **YAML scalar form**: a line of the shape
   `mode: server` (or `mode: "server"`) appears under any indentation
   AND no companion line sets a different `mode:` value.
3. **YAML list form**: an `auth.mode` (or top-level `mode:`) list whose
   *only* entry is `server`. Detected by an indentation-aware awk pass
   that collects the children of a `mode:` block-scalar list and flags
   when the collected set equals `{server}`.

`#` line comments and inline `# ...` tails are stripped before
matching. The flag normalizer drops `"`, `'`, `,`, `[`, `]` so
JSON-array `args: ["server","--auth-mode=server"]` and quoted
`"--auth-mode=server"` forms both match.

## Known false-positive notes

- A file that sets `--auth-mode=server` AND `--auth-mode=client` (or
  `--auth-mode=server,client`) is treated as good; the Argo Workflows
  server accepts comma-separated modes and the presence of any
  non-`server` mode means an authenticated path exists.
- A YAML list `[server, sso]` is treated as good for the same reason.
- A file that mentions the literal string `server` outside an
  `--auth-mode` context (e.g., `kind: Deployment` with `name:
  argo-server`) is not flagged; the YAML scalar rule requires the key
  to be `mode:`, not just any occurrence of the word `server`.
- Helm values files that quote the flag as
  `"--auth-mode=server,client"` are correctly classified as good
  because the comma-separated value contains a non-`server` mode.
