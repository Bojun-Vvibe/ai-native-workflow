# llm-output-grafana-default-admin-password-detector

Detects Grafana configurations that ship the built-in `admin` account
with the well-known default password `admin` (or fail to override it
on first boot), across the four common config surfaces:

* `grafana.ini` / `custom.ini`
* `docker-compose.yml` env (`GF_SECURITY_ADMIN_PASSWORD=admin`)
* Helm values (`adminPassword: admin`)
* Dockerfile / shell `ENV GF_SECURITY_ADMIN_PASSWORD admin`

## Why this matters

Grafana's first-boot admin credential is `admin` / `admin`. The
official docs ask the operator to change it interactively on first
login. In most LLM-generated quickstarts that step is silently
dropped: the dashboard ships to staging — and frequently to the open
internet — still answering `admin` / `admin`.

This is a different mechanism from anonymous-org-role and from
allow-embedding (the existing Grafana detectors): we are flagging
**default credentials**, not anonymous access. A site can have
anonymous access fully disabled and still be one HTTP POST away from
total takeover via the default admin login.

## Rules

A finding is emitted when the file is a recognised Grafana config
surface and the admin password is set to one of the canonical
defaults:

* literal `admin`
* literal `password`
* literal `grafana`
* the magic placeholder `change-me`, `changeme`, `CHANGE_ME`

…or when the surface declares the admin user but **omits** the
password entirely on a non-loopback listener (which lets Grafana
fall back to the built-in default).

Suppression: a magic comment `# grafana-default-admin-password-allowed`
anywhere in the file silences the finding (use only for
ephemeral CI containers that are torn down within the same job).

## Run

```
python3 detector.py examples/bad/01_grafana_ini_default.ini
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Out of scope

* Anonymous org role abuse — already covered by
  `llm-output-grafana-anonymous-org-role-admin-detector`.
* `allow_embedding` clickjacking — already covered by
  `llm-output-grafana-allow-embedding-detector`.
* Strength of *non-default* passwords — this detector only flags the
  well-known defaults, not weak-but-custom values.
