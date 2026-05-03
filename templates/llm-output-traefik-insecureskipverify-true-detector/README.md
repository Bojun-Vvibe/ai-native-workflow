# llm-output-traefik-insecureskipverify-true-detector

Stdlib-only Python detector that flags Traefik configurations setting
`insecureSkipVerify: true` (or any of its CLI / env / docker-label
equivalents). When this knob is on, Traefik will accept **any**
upstream TLS certificate — self-signed, expired, attacker-issued —
when proxying HTTPS to backends. It defeats the point of HTTPS to the
upstream and is a textbook **LLM "make the error go away" fix** for
`x509: certificate signed by unknown authority`.

Maps to:

- **CWE-295**: Improper Certificate Validation
- **CWE-297**: Improper Validation of Certificate with Host Mismatch
- **OWASP A02:2021** — Cryptographic Failures

## What we flag

Outside `#` / `//` / `;` comments:

1. YAML: `insecureSkipVerify: true` (any indentation, also lowercase
   `insecureskipverify`, also quoted `"true"` / `'true'`, also `yes` /
   `on`).
2. TOML: `insecureSkipVerify = true`.
3. CLI: `--serversTransport.insecureSkipVerify=true` (Traefik
   normalises case; we match either form).
4. Env: `TRAEFIK_SERVERSTRANSPORT_INSECURESKIPVERIFY=true`.
5. Docker label: `traefik.http.serversTransports.<name>.insecureSkipVerify=true`.

Each occurrence emits one finding line.

## What we accept (no false positive)

- `insecureSkipVerify: false` (production form).
- Production static config with `serversTransport.rootCAs:` pointing
  at the upstream CA bundle.
- Documentation comments demonstrating the bad form, e.g.
  `# DO NOT set insecureSkipVerify: true`.

## Why LLMs do this

When a generated stack uses Traefik in front of an HTTPS backend with
a private / self-signed cert, the first request fails with
`tls: failed to verify certificate`. The fastest "fix" any model will
suggest is `insecureSkipVerify: true` — because it works on the next
run and the prompt usually doesn't include "and keep TLS verification
on". This detector catches the regression at PR/CI time.

## Usage

```bash
python3 detect.py path/to/repo
python3 detect.py traefik.yml docker-compose.yml
```

Exit `0` if clean, `1` if any findings, `2` on usage error.

## Worked example

```
$ python3 detect.py examples/bad/*
examples/bad/01_static_yaml.yml:5: yaml-insecureSkipVerify-true:   insecureSkipVerify: true
...

$ python3 detect.py examples/good/*
$ echo $?
0
```

`smoke.sh` verifies bad=4/4 hit, good=0/3 hit. Run it from the
template directory.
