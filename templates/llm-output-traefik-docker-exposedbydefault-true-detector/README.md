# llm-output-traefik-docker-exposedbydefault-true-detector

Detect Traefik configuration snippets emitted by LLMs that leave the
Docker provider's `exposedByDefault` flag set to `true` (or omit it,
since the default is `true`).

## Why it matters

Traefik's Docker / Swarm provider has an `exposedByDefault` knob.
When it is true, **every** container on the host is auto-routed by
Traefik unless individually opted out with the
`traefik.enable=false` label. The recommended (opt-in) posture is:

```yaml
providers:
  docker:
    exposedByDefault: false
```

and then add `traefik.enable=true` on each container that should
actually be routed. LLMs commonly paste the "just works" example
straight from copy-paste tutorials, leaving `exposedByDefault: true`
or omitting it entirely.

## Rules

| # | Pattern | Why it matters |
|---|---------|----------------|
| 1 | YAML `exposedByDefault: true` (yes/on/1) | Every container auto-exposed |
| 2 | TOML `exposedByDefault = true` | Same as YAML, file-format variant |
| 3 | CLI flag `--providers.docker.exposedByDefault=true` | Same effect via command line |
| 4 | Env var `TRAEFIK_PROVIDERS_DOCKER_EXPOSEDBYDEFAULT=true` | Same effect via compose env |
| 5 | `providers.docker:` (or any docker provider config) without `exposedByDefault: false` AND without `constraints`/`defaultRule` filter | Default is `true`, so omission = expose all |

`#`-comments are stripped before matching, so a doc that *warns*
against the insecure default does not trigger.

## Suppression

Add `# traefik-expose-all-ok` anywhere in the file to disable all
rules (intentional all-expose dev box).

## Usage

```bash
python3 detector.py path/to/traefik.yml
python3 detector.py manifests/*.yaml
```

Exit code = number of files with at least one finding.

## Tests

```bash
python3 run_tests.py
```

Runs the detector against `examples/bad/*` (must all flag) and
`examples/good/*` (must all pass clean), printing
`PASS bad=4/4 good=0/3` on success.
