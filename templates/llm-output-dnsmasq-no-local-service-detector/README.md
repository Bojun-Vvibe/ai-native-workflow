# llm-output-dnsmasq-no-local-service-detector

Static detector for `dnsmasq` configurations that fall back to
**unscoped wildcard binding** because none of the standard scoping
directives is set. An unscoped dnsmasq instance answers recursive
DNS queries from anywhere on the network it can reach — a textbook
ingredient for a DNS amplification reflector and a frequent finding
in IoT / edge router firmware.

## What counts as scoped

The detector treats a config as **safe** if any one of these is
present:

- `local-service` (only answer same-subnet clients)
- `interface=<name>` (bind to one or more named interfaces)
- `listen-address=<ip>` where the address is **not** `0.0.0.0` /
  `::` / `[::]`

Equivalently, on the command line: `--local-service`,
`--interface=`, or `--listen-address=` with a non-wildcard address.

If none of the above is found, the file is flagged.

## Surfaces scanned

1. `dnsmasq.conf` and any file under a `dnsmasq.d/` directory
   (recognized by name, by `.conf` extension, or by content sniff
   for two or more dnsmasq directive keys).
2. `docker-compose.yml` / `Dockerfile` — any line containing
   `dnsmasq` is treated as an invocation and must include at least
   one scoping flag.

## When to use

- Reviewing LLM-emitted dnsmasq snippets for home-lab / edge-router
   / Pi-hole stand-in deployments.
- Pre-merge gate on infra repos that ship dnsmasq containers.
- Audit pass on appliance firmware build configs.

## Suppression

```
# dnsmasq-no-local-service-allowed
```

May appear on the same line as the finding, the line directly
above, or as a top-of-file marker. Use sparingly — only for
deliberately-public authoritative DNS deployments where dnsmasq
is **not** acting as a recursive resolver (e.g. `no-resolv` plus
explicit `address=` rules only).

## How to run

```sh
./verify.sh
```

Iterates every fixture under `examples/{bad,good}` and prints a
`bad=N/N good=0/N PASS` summary.

## Direct invocation

```sh
python3 detector.py path/to/dnsmasq.conf path/to/compose.yml
```

Exit code is the number of files with at least one finding (capped
at 255). Stdout lines are formatted `<file>:<line>:<reason>`.

## Limitations

- The detector does not parse `conf-file=` includes; point it at
  the included files explicitly if scoping lives there.
- A `bind-interfaces` directive without any `interface=` is still
  flagged because, with no interface list, dnsmasq still binds the
  wildcard.
- The detector does not check whether the host firewall blocks
  port 53 — config-only.
