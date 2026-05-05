# llm-output-unbound-remote-control-public-bind-detector

Detect unbound recursive resolver configurations that LLMs commonly
emit with the `remote-control` channel exposed to the network or
running plaintext. The unbound `unbound-control` interface accepts
operational commands like `reload`, `flush_zone`, `local_data` (a
direct cache-poisoning primitive: it lets the caller insert arbitrary
RR data that downstream resolvers will believe), `dump_cache`, and
`stop`. The hardening default is to bind the channel to `127.0.0.1`
(or `::1`) AND require an mTLS client certificate. Anything weaker
turns the resolver into a remote command shell.

When asked "set up unbound with remote control" or "how do I reload
unbound from my admin host", LLMs routinely:

- Set `control-enable: yes` together with `control-interface: 0.0.0.0`
  (or `::`, or a routable host address) "so I can manage it from my
  laptop".
- Set `control-use-cert: no` to "skip the cert dance", which makes the
  channel a plaintext TCP socket — credentials don't matter when the
  protocol itself is `reload\n`.
- Wrap `unbound-control` in a script that passes
  `-s 192.0.2.10@8953`, which only makes sense if the daemon side is
  already listening publicly.

This detector is orthogonal to every prior detector in the chain:

- `bind9` / `powerdns` / `dnsmasq` are different DNS server families
  with their own control surfaces; this targets the unbound recursive
  resolver specifically.
- `redis-no-requirepass`, `mosquitto-listener-no-tls`, etc. cover
  data-plane services. This targets a *control-plane* socket on a
  resolver, where successful commands rewrite cache contents.
- `kubelet-anonymous-auth-enabled` covers a Kubernetes node-agent;
  this covers a network-infrastructure daemon at a different layer of
  the stack.

Related weaknesses: CWE-306 (Missing Authentication for Critical
Function), CWE-319 (Cleartext Transmission of Sensitive Information),
CWE-668 (Exposure of Resource to Wrong Sphere).

## What bad LLM output looks like

Control channel listening on every interface:

```
remote-control:
  control-enable: yes
  control-interface: 0.0.0.0
  control-port: 8953
  control-use-cert: yes
```

Plaintext control channel — no client certificate required:

```
remote-control:
  control-enable: yes
  control-interface: 127.0.0.1
  control-use-cert: no
```

CLI wrapper aimed at a routable server address:

```sh
exec /usr/sbin/unbound-control -s 192.0.2.10@8953 reload
```

## What good LLM output looks like

- `remote-control` block omitted (control channel disabled — the
  default and the safest posture).
- `control-enable: yes` paired with `control-interface: 127.0.0.1`
  AND `control-use-cert: yes` AND a real key/cert pair.
- `unbound-control` invoked with no `-s` flag (talks to the local
  daemon over the loopback channel).

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/unbound_control_cli_public_server.sh
BAD  samples/bad/unbound_control_iface_v6_any.conf
BAD  samples/bad/unbound_control_iface_zero.conf
BAD  samples/bad/unbound_control_use_cert_no.conf
GOOD samples/good/unbound_control_cli_default.sh
GOOD samples/good/unbound_control_disabled.conf
GOOD samples/good/unbound_control_loopback_mtls.conf
GOOD samples/good/unbound_no_remote_control_block.conf
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero
good samples are flagged.

## Detector rules

A file is classified into exactly one of two modes; the YAML mode
wins when both an `unbound.conf` block and an `unbound-control`
invocation appear in the same file:

1. **`unbound.conf` with a `remote-control:` block.** The
   indentation-aware awk pass scans only fields nested under
   `remote-control:` (so a stray top-level `control-interface:` line
   in an unrelated context does not match). The block is flagged if
   `control-enable:` is `yes` AND either:
   - `control-use-cert:` is `no` (plaintext control), OR
   - any `control-interface:` value is not a loopback literal
     (`127.0.0.1`, `::1`, `localhost`, or `127.x.x.x`).
2. **`unbound-control` invocation** (no `unbound.conf` block in the
   same file). Flagged if the invocation passes
   `-s <host>@<port>` (or `--server=<host>@<port>`) where `<host>`
   is not a loopback literal — the daemon must be listening publicly
   for this to work.

`#` line comments and inline `# ...` tails are stripped before
matching. The CLI normalizer drops `"`, `,`, `[`, `]` so
`CMD ["unbound-control","-s","192.0.2.10@8953","reload"]` matches.

## Known false-positive notes

- A config that enables remote-control on the loopback with mTLS
  (`control-use-cert: yes` plus a key/cert pair) is treated as safe.
  Validating the cert pair itself is out of scope here — pair this
  detector with whatever process inspects the cert files.
- IPv6 loopback `::1` is treated as loopback. Link-local addresses
  (`fe80::/10`) are NOT treated as loopback — a control channel on a
  link-local address is reachable from anything else on the same L2
  segment and is unsafe.
- A multi-line config that lists several `control-interface:` entries
  is flagged if ANY entry is non-loopback — a single public binding
  is enough to expose the channel.
- The detector does not parse `include:` directives. If the
  `remote-control:` block is hidden behind an include the detector
  will defer; pair it with whatever process expands includes.
