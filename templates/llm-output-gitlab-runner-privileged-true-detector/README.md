# llm-output-gitlab-runner-privileged-true-detector

Static lint that flags GitLab Runner configurations (`config.toml`,
Helm `values.yaml`, k8s manifests, env-var overrides) where the
Docker / Kubernetes executor is given `privileged = true`, which
gives every CI job a fully privileged container — equivalent to
root on the runner host.

## Background

The GitLab Runner Docker and Kubernetes executors take a
`privileged` flag. With `privileged = true`:

- Docker executor: every job container is started with
  `docker run --privileged`. The container can load kernel modules,
  access every host device under `/dev`, mount arbitrary host
  filesystems, and run `docker` inside itself with full host
  access. A malicious `.gitlab-ci.yml` (or a compromised dependency
  pulled by a job) can trivially escape to the runner host and
  pivot to every other tenant on the runner.
- Kubernetes executor: pods get `securityContext.privileged: true`
  and can do the same on the node.

GitLab's own docs recommend running privileged mode **only** for
single-tenant runners that build container images, and even then
prefer rootless alternatives (kaniko, BuildKit rootless, buildah).

LLM-generated runner configs and Helm values routinely set
`privileged = true` "so docker-in-docker works", on shared runners
that accept jobs from any project — a textbook multi-tenant CI
escape.

## CWE

- [CWE-250: Execution with Unnecessary Privileges](https://cwe.mitre.org/data/definitions/250.html)
- Related: [CWE-732: Incorrect Permission Assignment for Critical Resource](https://cwe.mitre.org/data/definitions/732.html)

## What it catches

- `privileged = true` inside a `[runners.docker]` block in
  `config.toml`.
- `privileged = true` inside a `[runners.kubernetes]` block in
  `config.toml`.
- Helm-style `runners.privileged: true` in GitLab Runner Helm
  `values.yaml`.
- `privileged: true` inside a nested `kubernetes:` block in
  runner-style YAML.
- `--docker-privileged` flag in `gitlab-runner register` invocations
  (shell scripts, Dockerfiles).

## What it does *not* catch

- Pod-level `securityContext.privileged: true` outside a runner
  context (covered by `llm-output-k8s-pod-privileged-true-detector`).
- Capability grants short of full privileged mode
  (`cap_add = ["SYS_ADMIN"]` etc.) — those are a separate, also-bad
  smell tracked by a different detector.

## Remediation

- Set `privileged = false` (the safe default).
- If you need to build container images, use a rootless builder
  (kaniko, BuildKit rootless, buildah --isolation=chroot).
- For docker-in-docker on a single-tenant runner, scope the runner
  to a specific project via tags and lock it (`locked = true`,
  `run_untagged = false`) before flipping `privileged` on, and
  document the trust boundary.
- Rotate any credentials reachable from the runner host if shared
  privileged mode was ever live.

## Suppression

Add the comment marker `gitlab-runner-privileged-allowed` anywhere
in the file to suppress findings (intended for known single-tenant
image-builder runners with a documented trust boundary).

## Usage

```sh
python3 detector.py path/to/config.toml path/to/values.yaml
```

Exit code is the number of findings. `0` means clean.

## Verify

```sh
bash verify.sh
```

Smoke-test output on a clean tree:

```
bad=4/4 good=0/3
PASS
```

Every `examples/bad/*` fixture fires at least one finding; every
`examples/good/*` fixture is clean.
