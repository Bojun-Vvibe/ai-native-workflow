# llm-output-rancher-bootstrap-password-admin-detector

Flags Rancher Manager / Rancher Server deployment manifests that set
the bootstrap password to the literal `admin` -- the value used in
every "install Rancher in 5 minutes" tutorial and the placeholder
operators forget to rotate.

## What it detects

All gated by an in-file Rancher context token (`rancher`, `CATTLE_`,
`cattle-system`, `rancher/rancher`):

1. Helm values: `bootstrapPassword: admin`
2. Env / docker-compose: `CATTLE_BOOTSTRAP_PASSWORD=admin`
3. Helm CLI: `--set bootstrapPassword=admin`
4. systemd drop-in: `Environment=CATTLE_BOOTSTRAP_PASSWORD=admin`

## Why this is dangerous

Rancher uses the bootstrap password to create the initial `admin`
user on first login. Anyone reaching the Rancher UI before the
operator rotates it gets:

- **cluster-admin on every downstream Kubernetes cluster** Rancher
  manages -- Rancher mints kubeconfigs on demand;
- full read of cluster credentials, node SSH keys, registry creds
  and cloud-provider creds stored in Rancher's etcd;
- the ability to deploy arbitrary workloads into any managed
  cluster (RCE on every node);
- audit-log tampering and IDP / RBAC reconfiguration.

This is the worst-case "default credentials" finding because Rancher
is a fan-out point: one default password compromises every cluster
under management.

## CWE / OWASP refs

- **CWE-798**: Use of Hard-coded Credentials
- **CWE-1392**: Use of Default Credentials
- **CWE-521**: Weak Password Requirements
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A07:2021** -- Identification and Authentication Failures

## False positives

Skipped:

- Files with no Rancher context (an unrelated chart whose
  `bootstrapPassword: admin` value is unrelated to Rancher).
- Comment-only mentions of the default in documentation.
- Bootstrap password set to anything other than the literal `admin`
  (the detector targets the published default exactly).

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

Four `examples/bad/` files (Helm `values.yaml`, `docker-compose.yml`,
`install.sh` with `--set`, `rancher.service` systemd drop-in) each
trip the detector. Three `examples/good/` files (env-templated
values, env-templated compose, install script reading from a sealed
secret) all stay clean.
