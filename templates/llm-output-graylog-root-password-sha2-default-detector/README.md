# llm-output-graylog-root-password-sha2-default-detector

Flags Graylog server configurations that ship the well-known default
`root_password_sha2` value (SHA-256 of the literal string `"admin"`):

```
8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918
```

## What it detects

Three concrete forms:

1. `server.conf` / `.properties` — `root_password_sha2 = <default-hash>`
2. Env / docker-compose / `.env` — `GRAYLOG_ROOT_PASSWORD_SHA2=<default-hash>`
3. Helm values / k8s — `graylog.rootPasswordSha2: <default-hash>`

The default hash is published in Graylog's official docs and the
quickstart `docker-compose.yml`, so models reproduce it verbatim when
asked to "deploy Graylog".

## Why this is dangerous

Anyone who knows that public hash (i.e. anyone who can read the docs)
can authenticate as the local `admin` superuser and:

- read every search result, dashboard, stream, alert
- create / modify users and roles (tenant takeover)
- create input listeners (log injection / network pivot)
- query the underlying Elasticsearch / OpenSearch directly via
  search-result exfiltration

Logs typically contain secrets, JWTs, request bodies, and PII.

## CWE / OWASP refs

- **CWE-798**: Use of Hard-coded Credentials
- **CWE-1392**: Use of Default Credentials
- **CWE-521**: Weak Password Requirements
- **CWE-1188**: Insecure Default Initialization of Resource
- **OWASP A07:2021** — Identification and Authentication Failures

## False positives

The detector requires either:

- the key on the same line normalises to contain `rootpasswordsha2`, or
- the file as a whole contains `graylog` / `GRAYLOG_` context **and**
  the key name contains `password`.

Comments are ignored. Other (non-default) SHA-256 values for the same
key are not flagged. The literal hash inside prose / a comment is not
flagged.

## Usage

```sh
python3 detect.py path/to/graylog.conf
python3 detect.py path/to/dir/
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Verify

```sh
bash smoke.sh
# bad=4/4 good=0/3
# PASS
```
