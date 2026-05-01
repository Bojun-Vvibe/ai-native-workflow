# llm-output-spring-actuator-exposed-detector

Static lint that flags Spring Boot Actuator configurations exposing
sensitive management endpoints to the network without authentication-aware
narrowing.

Spring Boot's Actuator surface (`/actuator/env`, `/heapdump`,
`/threaddump`, `/loggers`, `/mappings`, `/configprops`, `/beans`,
`/jolokia`, `/shutdown`, `/refresh`, `/restart`, `/pause`, `/resume`,
`/trace`, `/auditevents`) is enormously useful in development and
extremely dangerous in production. When `management.endpoints.web` is
configured to expose `*` (or every dangerous endpoint by name) and the
service binds to a routable interface, an unauthenticated attacker can:

- Read environment variables (DB passwords, cloud-provider keys) via
  `GET /actuator/env`.
- Trigger a heap dump containing in-memory secrets via `/heapdump`.
- Change log levels and pivot to log4shell-style exploits via `/loggers`.
- POST to `/env` and reach RCE in older / mis-configured Spring Cloud
  setups.
- Issue `/shutdown`, `/restart`, `/pause`, or `/resume` to disrupt the
  service.

LLM-generated `application.properties`, `application.yml`, and
`bootstrap.yml` files routinely paste in:

```properties
management.endpoints.web.exposure.include=*
management.endpoint.shutdown.enabled=true
management.endpoint.env.post.enabled=true
management.security.enabled=false
management.endpoints.web.cors.allowed-origins=*
```

This detector flags those exposures.

## What it catches

- `management.endpoints.web.exposure.include=*` (every endpoint)
- `management.endpoints.web.exposure.include=...,env,heapdump,...`
  (any dangerous endpoint listed by name)
- `management.endpoint.shutdown.enabled=true`
- `management.endpoint.env.post.enabled=true`
- `management.security.enabled=false` (Spring Boot 1.x)
- `management.endpoints.web.cors.allowed-origins=*`

Also covers the equivalent YAML structures in `.yml` / `.yaml`, both the
deeply nested form (`management:` -> `endpoints:` -> ...) and the dotted
shorthand (`management.endpoints.web.exposure.include: '*'`).

## CWE references

- [CWE-200](https://cwe.mitre.org/data/definitions/200.html): Exposure of
  Sensitive Information to an Unauthorized Actor
- [CWE-732](https://cwe.mitre.org/data/definitions/732.html): Incorrect
  Permission Assignment for Critical Resource
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function

## False-positive surface

- Local-dev profiles intentionally exposing actuator behind `localhost`
  or behind a strict network policy. Suppress per line with a trailing
  `# actuator-exposure-allowed` comment.
- The `exclude` form (`management.endpoints.web.exposure.exclude=*`) is
  safe and is not flagged.
- A list that contains only `health,info` (the canonical
  liveness/readiness pair) is not flagged.

## Worked example

```sh
$ ./verify.sh
bad=5/5 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least one
  finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
