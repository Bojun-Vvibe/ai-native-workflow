# llm-output-memcached-listen-all-detector

Detect memcached config / launch snippets that expose the binary text or
UDP protocol to every interface without SASL or a loopback bind.

Memcached's stock build has **no authentication** — SASL must be enabled
both at compile time *and* via the `-S` flag at runtime, and most distro
packages ship without it. A `-l 0.0.0.0` (or any non-loopback bind)
without `-S` is therefore an unauthenticated cache read/write surface for
anything that can route to the host. The UDP listener is also the
classic amplification primitive abused in 2018-era reflection DDoS
campaigns; modern memcached packages default to `-U 0` for that reason.

Upstream guidance:

- memcached `README` and `man memcached` — `-l <addr>` "Listen on `<addr>`;
  default is INADDR_ANY"; `-S` "Turn on SASL authentication".
- memcached release notes for 1.5.6 (2018-02-27): UDP port disabled by
  default following CVE-2018-1000115 (UDP amplification).
- Debian / Ubuntu `/etc/memcached.conf` ships `-l 127.0.0.1` and `-U 0`
  for the same reason.

## What this catches

| Rule | Pattern | Why it matters |
|------|---------|----------------|
| 1 | CLI / systemd / Dockerfile / compose contains `-l 0.0.0.0` (or `--listen=0.0.0.0`) and **no** `-S` flag in the same launch line | Unauthenticated cache reachable from every routable interface |
| 2 | `/etc/memcached.conf` style file with an uncommented `-l 0.0.0.0` and no uncommented `-S` line | Same hole, persisted form |
| 3 | UDP enabled (`-U <non-zero>` / `--udp-port=<non-zero>`) without a loopback (`-l 127.x` / `::1` / `localhost`) bind | Re-enables the UDP amplification vector |
| 4 | JSON-array `command:` form (compose / k8s) that triggers rule 1 or rule 3 — quote/comma-separated tokens are tolerated | Same patterns, just expressed differently |

To reduce false positives the detector first checks that the file or its
contents reference `memcache(d)` — a stray `-l 0.0.0.0` in unrelated
firewall docs will not trip it. Comment-only lines (`# -l 0.0.0.0`) are
ignored so that documentation warning *against* the insecure default is
safe.

## What bad LLM output looks like

```ini
# /etc/memcached.conf
-l 0.0.0.0
-p 11211
-m 64
```

```yaml
# docker-compose.yml
services:
  cache:
    image: memcached:1.6
    command: ["memcached", "--listen=0.0.0.0", "-p", "11211"]
    ports: ["11211:11211"]
```

```ini
# systemd unit — re-enables UDP amplification
ExecStart=/usr/bin/memcached -l 0.0.0.0 -p 11211 -U 11211 -m 256
```

## What good LLM output looks like

```ini
# Loopback bind, UDP off — distro default
-l 127.0.0.1
-p 11211
-U 0
-m 64
```

```ini
# Public bind is fine when SASL is on
-l 0.0.0.0
-p 11211
-U 0
-S
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
BAD  samples/bad/01-listen-all.conf
BAD  samples/bad/02-systemd-udp-amplification.service
BAD  samples/bad/03-compose-public.yml
BAD  samples/bad/04-dockerfile-public-udp.Dockerfile
GOOD samples/good/01-loopback-bind.conf
GOOD samples/good/02-sasl-enabled.conf
GOOD samples/good/03-compose-loopback.yml
GOOD samples/good/04-warning-doc.md
bad=4/4 good=0/4 PASS
```
