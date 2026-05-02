# llm-output-docker-daemon-tcp-no-tls-detector

Detect snippets that bind the Docker daemon API to a TCP socket without
TLS / mutual-auth — typically the well-known plaintext port `2375`.

The Docker daemon API has **no built-in authentication**. Anyone who can
reach `tcp://host:2375` can issue `docker run -v /:/host --privileged …`
and obtain root on the host filesystem. Upstream documentation is
unambiguous: the only supported way to expose the daemon over the
network is `--tlsverify` with a CA-signed client certificate, conventionally
on port `2376`.

Upstream guidance:

- Docker docs, "Protect the Docker daemon socket":
  > By default, Docker runs through a non-networked UNIX socket … If you
  > need Docker to be reachable through the network in a safe manner,
  > you can enable TLS … Docker daemon listens on `2376` for encrypted
  > traffic and `2375` for unencrypted traffic.
- CIS Docker Benchmark §2.4 / §2.5 — "Ensure Docker is allowed to make
  changes to iptables" and "Ensure insecure registries are not used"
  call out the same plaintext-API hole as a known critical finding.

## What this catches

| Rule | Pattern | Why it matters |
|------|---------|----------------|
| 1 | `dockerd … -H tcp://…` (or `--host=tcp://…`) on a line with no `--tlsverify` / `--tlscacert` / `--tls(=true)` | Plaintext API = root on the host |
| 2 | `systemd` unit `ExecStart=` with the same shape | Persistent form of rule 1 |
| 3 | `daemon.json` `"hosts": [..., "tcp://..."]` with no `"tlsverify": true`, `"tls": true`, or `"tlscacert"` | Plaintext API via the canonical config file |
| 4 | Any uncommented binding to port `2375` (the well-known plaintext port) without TLS flags | Catches `0.0.0.0:2375` shorthand even outside an obvious dockerd context |
| 5 | Compose / k8s `command:` array form for `dockerd` with `-H tcp://` and no TLS flags | Same hole, JSON-array shape |

A gate filter requires the file or its name to mention `dockerd` /
`docker` / `daemon.json` to keep unrelated TCP configs from being flagged.
The `-H tcp://` rule is evaluated **per line** so a TLS flag on a
different `dockerd` invocation cannot whitewash a plaintext one elsewhere
in the same file. Comment-only lines are ignored, so warning docs are
safe.

## What bad LLM output looks like

```ini
# /etc/systemd/system/docker.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd -H fd:// -H tcp://0.0.0.0:2375
```

```json
{
  "hosts": ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2375"]
}
```

```yaml
services:
  dockerd:
    image: docker:24-dind
    command: ["dockerd", "-H", "tcp://0.0.0.0:2375"]
```

## What good LLM output looks like

```ini
ExecStart=/usr/bin/dockerd -H fd://
```

```json
{
  "hosts": ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2376"],
  "tlsverify": true,
  "tlscacert": "/etc/docker/ca.pem",
  "tlscert":  "/etc/docker/server-cert.pem",
  "tlskey":   "/etc/docker/server-key.pem"
}
```

## Sample layout

```
samples/
  bad/   # 4 files; every file MUST be flagged
  good/  # 4 files; no file may be flagged
```

## Verified result

```
$ bash detect.sh samples/bad/* samples/good/*
BAD  samples/bad/01-systemd-tcp-2375.conf
BAD  samples/bad/02-daemon-json-no-tls.json
BAD  samples/bad/03-dockerd-cli.sh
BAD  samples/bad/04-compose-dind-plaintext.yml
GOOD samples/good/01-systemd-unix-only.conf
GOOD samples/good/02-daemon-json-mtls.json
GOOD samples/good/03-dockerd-mtls.sh
GOOD samples/good/04-warning-doc.md
bad=4/4 good=0/4 PASS
```
