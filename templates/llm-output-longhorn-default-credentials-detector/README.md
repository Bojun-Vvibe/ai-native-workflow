# llm-output-longhorn-default-credentials-detector

Flags Longhorn (Kubernetes block-storage) install manifests / scripts
that protect the Longhorn UI with the literal default basic-auth
credentials shown in nearly every Longhorn quickstart -- typically
`admin:admin` baked into an htpasswd-backed nginx-ingress
`auth-secret`, or no auth annotation at all on the Longhorn UI
Ingress.

## What it detects

All gated by an in-file Longhorn context token (`longhorn`,
`longhorn-system`, `longhorn-frontend`, `longhorn.io`):

1. `htpasswd -b[c] <file> admin admin` in install scripts.
2. A Kubernetes `Secret` whose `auth:` value begins with `admin:`
   inside a Longhorn-context file (the documented quickstart
   pattern).
3. An `Ingress` whose backend points at `longhorn-frontend` on a
   non-empty `host:` but lacks
   `nginx.ingress.kubernetes.io/auth-type: basic`.

## Why this is dangerous

Longhorn has no native authentication on its UI. The UI is the
**cluster volume admin plane** -- whoever reaches it can:

- snapshot, restore, or **delete any PersistentVolume** in the
  cluster (full data loss);
- mount any volume into an attacker-chosen workload to read
  raw block contents (full data exfiltration -- bypasses
  pod-level RBAC and namespace isolation);
- alter replica count / drain a node to provoke availability
  loss;
- exfiltrate backup target credentials (S3 / NFS) configured
  in Longhorn settings.

`admin:admin` is the literal value the quickstart htpasswd line
produces; combined with the public docs hash it is effectively
unauthenticated. A Longhorn UI Ingress with no auth annotation
at all is strictly worse.

## CWE / OWASP refs

- **CWE-798**: Use of Hard-coded Credentials
- **CWE-1392**: Use of Default Credentials
- **CWE-306**: Missing Authentication for Critical Function
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A07:2021** -- Identification and Authentication Failures

## False positives

Skipped:

- Files with no Longhorn context (an unrelated nginx basic-auth
  Secret with `auth: admin:...` for a different service).
- Comment-only mentions of the default in docs.
- Ingresses that target `longhorn-frontend` AND carry the
  `auth-type: basic` annotation (an htpasswd whose contents are
  *not* `admin:admin` is out of this detector's scope; a separate
  weak-password detector should cover that).

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

Four `examples/bad/` files (an `install.sh` running `htpasswd -bc
auth admin admin`, an `auth-secret.yaml` with `auth: admin:$apr1$...`,
an `ingress.yaml` exposing `longhorn-frontend` on a public host with
no auth annotation, and a `helm-values.yaml` exposing the same with
no auth) each trip the detector. Three `examples/good/` files (an
`install.sh` that reads the username from an env var, an
`ingress.yaml` carrying the `auth-type: basic` annotation, and an
`auth-secret.yaml` whose entry starts with a non-default username)
all stay clean.
