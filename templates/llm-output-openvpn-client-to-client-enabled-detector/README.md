# llm-output-openvpn-client-to-client-enabled-detector

Static lint that flags OpenVPN **server** configs which enable
`client-to-client` (intra-tunnel forwarding inside the OpenVPN
process) and / or `duplicate-cn` (allow multiple clients to present
the same Common Name). Both are LLM-default footguns when asked for
"a working OpenVPN server config".

## Why this matters

`client-to-client` short-circuits the kernel's FORWARD chain — packets
between two connected VPN clients are relayed inside the `openvpn`
process and **never** hit `iptables` / `nftables` rules on the VPN
host. Operators who think "VPN users can't talk to each other because
my firewall blocks `tun0 -> tun0`" are simply wrong: with
`client-to-client` on, that firewall path is bypassed.

`duplicate-cn` removes the "one connection per client cert" guarantee.
A single stolen client certificate then grants concurrent mesh access
to every other connected user.

The two together are the classic shared-credential lateral-movement
shape: one phished cert, full reachability to every other VPN user as
if they were on the same L2 segment.

## What it catches

The file must look like an OpenVPN **server** config (presence of
`server`, `server-bridge`, `mode server`, `tls-server`, `push "..."`,
`ifconfig-pool`, or `client-config-dir`). Then any of:

1. `client-to-client` directive uncommented.
2. `duplicate-cn` directive uncommented.
3. `client-to-client` together with `verify-client-cert none`
   (or the legacy `client-cert-not-required`) — intra-tunnel
   forwarding without per-client cert auth.

OpenVPN treats both `#` and `;` as comment markers; both are stripped
before the directive match (column-0 indentation does not matter).

## What it accepts as safe

- Client-side configs (`client`, `remote ...`, `nobind`).
- Server configs that comment out `client-to-client` / `duplicate-cn`.
- Files annotated with `# openvpn-c2c-allowed` (closed-lab, single-
  tenant overlays).

## CWE references

- [CWE-668](https://cwe.mitre.org/data/definitions/668.html): Exposure
  of Resource to Wrong Sphere.
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html): Improper
  Access Control.
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function (when paired with
  `verify-client-cert none`).

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

Per-finding output for one bad sample:

```sh
$ python3 detector.py examples/bad/03-c2c-and-verify-none.conf
examples/bad/03-c2c-and-verify-none.conf:9:client-to-client enabled WITH verify-client-cert none (line 10) — intra-tunnel forwarding without per-client cert auth
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  prints `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag (4 fixtures).
- `examples/good/` — expected to pass clean (4 fixtures).
