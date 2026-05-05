# llm-output-calibre-web-default-admin-detector

Stdlib-only Python detector that flags **Calibre-Web**
(janeczku/calibre-web) deployments that ship with the documented
first-run default credentials `admin` / `admin123` without rotation,
or that pre-seed those credentials into the config / env / SQL
bootstrap. Maps to **CWE-798** (use of hard-coded credentials),
**CWE-521** (weak password requirements), and **CWE-1392** (use of
default credentials).

Calibre-Web's admin role grants more than "edit metadata of the
e-book library". It can:

- run shell-style conversion commands via the optional `UPLOAD` and
  `CONVERTERTOOL` settings (a documented path to RCE through the
  e-book converter pipeline),
- configure SMTP credentials and an arbitrary sender (credential
  exfiltration vector),
- create / promote arbitrary users.

Shipping the default `admin` / `admin123` on a public bind therefore
collapses to "remote code execution + credential leak primitive,
one HTTP POST away".

LLMs reach for `admin123` because it is the documented quick-start
password printed in the upstream README and in the linuxserver
container init script. The user is told to log in and change it; in
practice the change is never persisted into IaC, the env var
`ADMIN_PASSWORD=admin123` is templated into Compose, and the
container redeploys back to the default on every restart.

## Heuristic

We flag, outside `#` / `;` / `--` / `//` comment lines, any of:

1. Env override that pre-seeds the documented default password:
   `CALIBRE_WEB_ADMIN_PASSWORD=admin123`,
   `CALIBRE_WEB_PASSWORD=admin123`,
   `CALIBREWEB_ADMIN_PASSWORD=admin123`,
   or the linuxserver shorthand `ADMIN_PASSWORD=admin123`.
2. SQL bootstrap that inserts `('admin', 'admin123', ...)` into the
   `user` (or `users`) table — raw plaintext form.
3. SQL bootstrap that inserts `admin` paired with the well-known
   MD5 (`0192023a7bbd73250516f069df18b500`) or SHA-1
   (`7c4a8d09ca3762af61e59520943dc26494f8941b`) hash of `admin123`.
4. JSON / YAML config key `admin_password: admin123` or
   `default_admin_password: admin123` in a calibre-web context (file
   path contains `calibre`, or the file mentions `calibre-web`,
   `calibreweb`, `janeczku`, `app.db`, `CALIBRE_DBPATH`, or
   `/books`).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-798**: Use of Hard-coded Credentials.
- **CWE-521**: Weak Password Requirements.
- **CWE-1392**: Use of Default Credentials.
- Calibre-Web upstream README: documented first-run credentials are
  username `admin`, password `admin123`, with an explicit "change
  immediately" warning that IaC routinely ignores.

## What we accept (no false positive)

- `ADMIN_PASSWORD=...` set to anything other than `admin123` (we
  match on the literal default value).
- `CALIBRE_WEB_USER=admin` alone (the username is a label, not the
  vulnerability — the password is).
- Commented-out lines (`# ADMIN_PASSWORD=admin123`,
  `-- INSERT INTO user VALUES ('admin','admin123',...);`).
- A generic `admin_password: admin123` in a config that has no
  calibre-web context marker (other apps' detectors own their own
  defaults).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       4 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/.env
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

`admin123` is the first thing in the upstream Calibre-Web README and
in the linuxserver container's first-run log. An LLM asked "how do I
auto-provision the calibre-web admin user in my Compose stack" will
emit exactly `ADMIN_PASSWORD=admin123` or the equivalent SQL seed.
The developer accepts because "the docs say that's the default", the
Compose ships, the container is exposed via reverse proxy, and the
default never gets rotated. The detector exists to catch the paste
before it ships.
