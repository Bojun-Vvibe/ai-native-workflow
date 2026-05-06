# llm-output-sftpgo-default-admin-credentials-detector

Detect SFTPGo configurations that LLMs commonly emit with the
upstream default / first-run admin credentials baked in. SFTPGo is a
self-hosted SFTP/HTTP/WebDAV file server; its WebAdmin UI runs on
port 8080 by default and grants full filesystem and user
administration. With default credentials present in the rendered
config, anyone who can reach that port (often `0.0.0.0:8080` in the
same generated configs) becomes the SFTPGo super-admin.

When asked "give me a `sftpgo.json` config" or "Docker-compose for
SFTPGo", models routinely:

- Set `data_provider.create_default_admin: true` (or
  `SFTPGO_DATA_PROVIDER__CREATE_DEFAULT_ADMIN=1`) without also
  setting `default_admin_username` / `default_admin_password` to
  non-default values — the boot creates `admin` / `password`.
- Hard-code the literal first-run credentials (`admin` /
  `password`, `admin` / `admin`, `sftpgo` / `sftpgo`, `admin` /
  `changeme`) into `default_admin_username` /
  `default_admin_password`.
- Pass `SFTPGO_DEFAULT_ADMIN_USERNAME=admin` and
  `SFTPGO_DEFAULT_ADMIN_PASSWORD=password` (or the same
  placeholders) via Docker / systemd unit env.

## Bad patterns

1. SFTPGo JSON / YAML config with `create_default_admin: true`
   AND no `default_admin_password` set OR
   `default_admin_password` is in the well-known placeholder set
   (`password`, `admin`, `sftpgo`, `changeme`, `change_me`,
   `please_change_me`, `secret`, empty string).
2. Docker / systemd / `.env` exporting
   `SFTPGO_DATA_PROVIDER__CREATE_DEFAULT_ADMIN=1` AND
   `SFTPGO_DATA_PROVIDER__DEFAULT_ADMIN_PASSWORD` matching the
   placeholder set (or unset entirely).
3. SFTPGo config / env where `default_admin_username` is the
   placeholder `admin` / `sftpgo` / `root` AND
   `default_admin_password` is also a placeholder.

## Good patterns

- `create_default_admin: false` (operator runs `sftpgo initprovider`
  + `sftpgo gen admin` or seeds via REST API).
- `create_default_admin: true` with a `default_admin_password` that
  is not in the placeholder set (e.g. a long random string or a
  `${SECRET_REF}` substitution).
- Docker env that overrides
  `SFTPGO_DATA_PROVIDER__DEFAULT_ADMIN_PASSWORD` to a non-placeholder
  value sourced from a secret manager.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Expected: `bad=4/4 good=0/4 PASS`.

## Why this matters

SFTPGo's bootstrap flow is intentionally one-line-friendly: enabling
`create_default_admin` makes the very first start spin up an `admin`
account. Upstream documentation and Docker examples historically used
the placeholder `password` / `admin` to demonstrate the feature.
LLMs that have ingested those examples reproduce them verbatim,
producing publicly-reachable WebAdmin UIs that an attacker logs into
by typing `admin` / `password`.
