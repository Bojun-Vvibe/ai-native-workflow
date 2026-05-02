# llm-output-sonarqube-default-admin-detector

## Problem

SonarQube ships exactly one bootstrap account: `admin` / `admin`.
Headless or container-based deployments routinely never rotate it.
Once that pair is reachable, the Sonar Web API at `/api/users/*`,
`/api/settings/set`, and the plugin upload endpoint at
`/deploy/plugins` all accept it — and SonarQube plugins are JARs
that load straight into the SonarQube JVM. Default admin = RCE on
the Sonar host.

LLM-generated provisioning artifacts (Dockerfiles, Helm values
files, CI scripts, READMEs) frequently re-introduce the default
credential in one of a handful of mechanical shapes. This detector
catches them statically before they ship.

## What the insecure pattern looks like

Any of these in a non-comment line:

```sh
# 1. curl using default basic-auth credentials
curl -u admin:admin https://sonar.example.com/api/system/health

# 2. environment / dotenv / yaml / ini
SONAR_ADMIN_PASSWORD=admin

# 3. sonar-scanner properties
sonar.login=admin
sonar.password=admin

# 4. raw HTTP header carrying base64("admin:admin")
Authorization: Basic YWRtaW46YWRtaW4=

# 5. literal "admin" used in place of a real Sonar token
SONAR_TOKEN=admin
```

## What a safe configuration looks like

  * Rotate the bootstrap password on first launch (the
    `/api/users/change_password` API or the first-run UI).
  * Issue per-CI **Sonar tokens** (`/account/security`) and pass
    them via `SONAR_TOKEN` from a secret store — never the literal
    string `admin`.
  * Keep `sonar.login` / `sonar.password` out of checked-in
    `sonar-project.properties`; pass tokens via env at scan time.

## How the detector works

`detector.py` strips common single-line comments (`#`, `//`, `--`,
`;`) and `/* ... */` block comments, then matches five regex
patterns against the remainder:

  1. `-u admin:admin` / `--user admin:admin` (curl, httpie style)
  2. `SONAR_ADMIN_PASSWORD = admin` (env / dotenv / yaml / ini)
  3. `sonar.login=admin` paired with `sonar.password=admin`
  4. `Authorization: Basic YWRtaW46YWRtaW4=`
  5. `SONAR_TOKEN=admin`

A file containing the marker `sonarqube-default-admin-allowed` is
skipped (useful for example fixtures inside docs).

The script's exit code equals the number of findings.

## Run it

```sh
python3 detector.py path/to/bootstrap.sh
```

End-to-end self-check:

```sh
bash verify.sh
```

The verifier prints one line of the form
`bad=N/N good=0/N` followed by `PASS` or `FAIL`.
