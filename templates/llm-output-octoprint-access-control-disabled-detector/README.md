# llm-output-octoprint-access-control-disabled-detector

Stdlib-only Python detector that flags **OctoPrint** configurations
which disable the access control system. Maps to **CWE-306** (missing
authentication for critical function), **CWE-1188** (insecure default
initialization of resource), and **CWE-284** (improper access
control).

OctoPrint's HTTP API is the same surface the web UI talks to: it can
upload G-code, start a print, send raw G-code commands directly to
the printer's serial port, change the bed/hotend temperature setpoint,
and on most installs read/write arbitrary paths through the file
manager plugin. The thermal runaway protection that prevents a
malicious print from setting fire to a 3D printer lives in the
firmware, not in OctoPrint, and on plenty of cheap printers it is
either misconfigured or absent. An OctoPrint instance with access
control disabled and reachable on a routable interface is therefore
a remote-physical-damage primitive, not just an "anyone can pause my
print" annoyance.

LLMs reach for `accessControl: {enabled: false}` because it is the
canonical one-liner to skip the first-run wizard in a Docker
deployment ("just run it headless, I'll add auth later"). The change
ships in a `docker-compose.yaml`, the container binds `0.0.0.0:5000`,
and the printer is on the open Internet inside the hour.

## Heuristic

We flag any of the following, outside `#` comment lines:

1. config.yaml block-form:
   ```
   accessControl:
     enabled: false
   ```
   (detected by tracking the `accessControl:` block by indentation
   and matching the `enabled: false` child).
2. Inline / flow-style: `accessControl: {enabled: false}`.
3. CLI flag `--no-access-control` on an `octoprint serve` invocation
   (Dockerfile CMD/ENTRYPOINT, shell wrapper, systemd `ExecStart`,
   k8s `args`).
4. Environment-variable override
   `OCTOPRINT_ACCESS_CONTROL_ENABLED=false` (used by
   `octoprint/octoprint` and `outpostzero/octoprint` templated
   container images).
5. Top-level `firstRun: false` paired with **no** `accessControl:`
   section in the same `config.yaml` — the first-run wizard is
   skipped and nothing creates the admin account, so the instance
   ships with anonymous admin.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-284**: Improper Access Control.
- OctoPrint docs: the access control system is enabled by default;
  the first-run wizard refuses to advance until an admin account is
  created. Disabling it is documented as "only for trusted, isolated
  networks" — exactly the assumption that breaks the moment the
  container ships with `0.0.0.0:5000`.

## What we accept (no false positive)

- `accessControl: {enabled: true}` (the default).
- An `accessControl:` block with `enabled: true` and any other child
  keys (`autologinLocal`, `localNetworks`, `userManager`).
- `firstRun: false` paired with an `accessControl:` section
  (i.e. the operator templated the admin account through a
  configuration management tool instead of running the wizard).
- Commented-out lines (`# accessControl: {enabled: false}`).
- Documentation / Markdown mentions (we only scan config-shaped
  files).
- Other keys that happen to share the prefix
  (`accessControlList`, `accessControlPolicy`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       4 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/config.yaml
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

"How do I skip the OctoPrint setup wizard in Docker?" is a frequent
question on community forums; the most-upvoted answer is invariably
`accessControl: {enabled: false}` plus `firstRun: false`. An LLM
trained on those threads will offer it as a one-line fix to a
developer who wants `docker compose up` to land them straight in the
UI. The detector exists to catch the paste before the printer sits
on the open Internet under anonymous admin.
