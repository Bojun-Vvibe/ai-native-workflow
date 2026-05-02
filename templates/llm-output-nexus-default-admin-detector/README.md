# llm-output-nexus-default-admin-detector

Static lint that flags Sonatype Nexus Repository Manager 3 deployment
artifacts which ship the well-known default admin credential
`admin/admin123` — or which disable the first-boot random-password
mechanism without supplying a real replacement.

Patterns recognized:

- `NEXUS_SECURITY_INITIAL_PASSWORD=admin123` (or any trivial value)
- `-Dnexus.security.initialPassword=admin` JVM flag with trivial value
- `NEXUS_SECURITY_RANDOMPASSWORD=false` *without* a paired
  non-trivial `initialPassword` — Nexus then falls back to the
  documented static default `admin123`
- `COPY admin.password /nexus-data/admin.password` (Dockerfile
  baking the bootstrap secret into an image layer)
- `docker-compose` volume mount of a static `admin.password` into
  `/nexus-data/admin.password`
- Provisioning shell snippets that POST/PUT to
  `/service/rest/v1/security/users/admin/change-password` with a
  trivial body

## Why this matters

Nexus 3's first-boot random-password file
(`/nexus-data/admin.password`) is intended to be read once,
exchanged for a real password, and deleted. LLM-suggested Dockerfiles
routinely "fix" the inconvenience by hard-coding `admin123`, baking
the bootstrap file into the image, or scripting a REST call that
re-sets the password to the same default. Nexus is internet-facing
in a huge fraction of CI/CD topologies (it's a binary cache used by
build agents), and a default admin gives full upload, deletion, and
proxy-rewrite power over every artifact downstream of the build.

This detector is **orthogonal** to "no TLS" / "anonymous read"
detectors. It only fires on the credential-strength misconfig.

## CWE references

- [CWE-798](https://cwe.mitre.org/data/definitions/798.html): Use of
  Hard-coded Credentials
- [CWE-1392](https://cwe.mitre.org/data/definitions/1392.html): Use of
  Default Credentials
- [CWE-256](https://cwe.mitre.org/data/definitions/256.html):
  Plaintext Storage of a Password

## What it accepts

- Values that look like unresolved templating: `${...}`, `$(...)`,
  `<<TOKEN>>`, `{{ .Values.x }}`.
- Files containing the marker `# nexus-default-admin-allowed`
  (e.g. ephemeral CI fixtures, throwaway test images).
- A non-trivial `initialPassword` paired with `randompassword=false`.

## False-positive surface

- A trivial admin **username** alone is not flagged; the password is
  the secret.
- REST change-password calls whose body is templated
  (`-d "$NEW_PW"`) are not flagged.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

Per-finding output:

```sh
$ python3 detector.py examples/bad/01-Dockerfile
examples/bad/01-Dockerfile:3:NEXUS_SECURITY_INITIAL_PASSWORD set to trivial/default value 'admin123' — Nexus admin password must be unique per environment
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
