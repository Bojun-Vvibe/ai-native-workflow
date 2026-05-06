# llm-output-vouch-proxy-jwt-secret-default-detector

Stdlib-only Python detector that flags **Vouch Proxy** (SSO
reverse-proxy used in front of nginx / traefik to gate apps behind
OAuth/OIDC) deployments where `vouch.jwt.secret` (env:
`VOUCH_JWT_SECRET`) is left at the upstream example placeholder, an
obvious weak literal, or an empty string.

Maps to **CWE-798** (Hard-coded Credentials), **CWE-1392** (Use of
Default Credentials), **CWE-330** (Insufficiently Random Values),
**CWE-1188** (Insecure Default Initialization), **CWE-347**
(downstream: Improper Verification of Cryptographic Signature, since
the forged JWT will be accepted), OWASP **A02:2021 Cryptographic
Failures**, **A05:2021 Security Misconfiguration**, **A07:2021
Identification & Authentication Failures**.

## Why this is a problem

Vouch Proxy is a tiny Go service whose entire job is to mint a
signed JWT cookie after a successful OAuth/OIDC flow, and let
downstream nginx / traefik validate it via a cheap `/validate`
sub-request. Every app behind Vouch trusts whatever HMAC-signed JWT
the cookie carries.

If the attacker knows `jwt.secret`, they can:

- forge a `VouchCookie` JWT for an arbitrary email / group
- present it to nginx → nginx calls Vouch `/validate` → 200
- pass straight through to every protected backend

That is total SSO bypass, with one curl, with no OAuth flow.

## Why LLMs ship this

The upstream `config/config.yml.example` ships with:

```yaml
jwt:
  secret: your_random_string
```

and the env-var template ships with:

```sh
VOUCH_JWT_SECRET=your_random_string
```

Every "Vouch in 5 minutes" tutorial copies these literals verbatim.
Models reproduce them exactly, or fall back to obvious placeholders
(`changeme`, `secret`, `vouch`) when generating compose files from
scratch.

## Heuristic

In `vouch*`-named files, `config.y*ml`, `*.env*`, `*.conf`, `*.sh`,
`Dockerfile*`, `docker-compose.*`, `*.toml`, `*.json`, and any file
whose body matches Vouch scope hints (`vouch-proxy`, `vouch.jwt`,
`quay.io/vouch/vouch-proxy`, etc.), we flag:

1. A YAML `jwt:` block with `secret: <weak>` underneath.
2. An env-style `VOUCH_JWT_SECRET=<weak>` /
   `VOUCH_JWT_SECRET: <weak>`.

`<weak>` is one of:

- empty string
- `your_random_string` (upstream example)
- `change_me`, `changeme`, `change-me`, `changeit`
- `secret`, `password`, `default`, `test`, `demo`, `example`
- `vouch`, `vouch-proxy`, `jwt`, `jwtsecret`
- `admin`, `root`, `12345*`, `qwerty`, `letmein`
- any value < 32 chars (HMAC-SHA256 needs >= 256 bits of entropy;
  we approximate with length).

We do NOT flag:

- `${...}` / `{{ ... }}` template references — assume the real
  value is injected from a secret store at runtime.
- Long high-entropy values (>= 32 chars).
- `.md` / `.rst` / `.txt` / `.adoc` prose.
- Files with no Vouch scope hint.

## Usage

```sh
python3 detect.py path/to/file_or_dir [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

## Worked example

```sh
$ cd templates/llm-output-vouch-proxy-jwt-secret-default-detector
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

## Fixtures

`examples/bad/`:

- `01_docker-compose.yml` — `VOUCH_JWT_SECRET: your_random_string`.
- `02_vouch.env.example` — `VOUCH_JWT_SECRET=changeme`.
- `03_config.yml` — YAML `jwt.secret: your_random_string`.
- `04_run_vouch.sh` — shell wrapper exporting `VOUCH_JWT_SECRET=secret`.

`examples/good/`:

- `01_docker-compose.yml` — `${VOUCH_JWT_SECRET}` injected.
- `02_vouch.env.example` — long high-entropy hex secret.
- `03_config.yml` — `{{ vouch_jwt_secret_from_vault }}` template ref.
- `04_doc_only.md` — README mentioning the placeholder string in
  prose; `.md` is not scanned.

## Suggested remediation

```sh
openssl rand -hex 48 | sudo tee /etc/vouch/jwt.secret
chmod 600 /etc/vouch/jwt.secret
chown vouch:vouch /etc/vouch/jwt.secret
```

```yaml
vouch:
  jwt:
    secret: "{{ lookup('file', '/etc/vouch/jwt.secret') }}"
    maxAge: 240
```

Front Vouch Proxy on a private interface (`127.0.0.1` or a private
subnet); only nginx / traefik should ever call it. Rotate the JWT
secret on a schedule, and on rotation invalidate every existing
`VouchCookie` by bumping the cookie name suffix.
