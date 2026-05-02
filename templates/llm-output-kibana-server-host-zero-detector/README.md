# llm-output-kibana-server-host-zero-detector

Static lint that flags Kibana `kibana.yml` files where `server.host` is
set to `"0.0.0.0"` (or `0`, `"0"`, `"::"`, `"*"`) — i.e. binding the
Kibana web UI to every network interface — without an authentication
mechanism in front of it (no `xpack.security.enabled: true`, no
`server.ssl.enabled: true` + reverse-proxy auth comment).

Kibana's default `server.host` is `localhost`. LLM-generated configs
routinely "fix the can't-connect-from-outside" problem by changing it
to `0.0.0.0`, accidentally publishing the dashboard — and any indices
it can read — to the wider network.

## What it catches

- `server.host: "0.0.0.0"` (and unquoted / single-quoted variants).
- `server.host: 0`, `server.host: "0"`, `server.host: "::"`,
  `server.host: "*"`.
- Same shape with extra leading whitespace (YAML allows).
- Combined with `xpack.security.enabled: false` → flagged with an
  extra "no auth" finding.

## CWE references

- [CWE-668](https://cwe.mitre.org/data/definitions/668.html): Exposure
  of Resource to Wrong Sphere
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html): Exposure
  of Sensitive Information to an Unauthorized Actor

## False-positive surface

- Containerized Kibana that is genuinely fronted by an
  authenticating reverse proxy on a private network. Suppress per
  file with a comment `# kibana-bind-all-allowed` anywhere in the
  file.
- `server.host: "127.0.0.1"` / `localhost` / a specific private IP
  is treated as safe.
- `xpack.security.enabled: true` downgrades the bind-all finding to
  an info-level "still listening on all interfaces" note that does
  not affect exit code.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
