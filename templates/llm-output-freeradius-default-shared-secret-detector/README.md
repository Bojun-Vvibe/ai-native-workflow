# llm-output-freeradius-default-shared-secret-detector

Static lint that flags FreeRADIUS / RADIUS-shape configurations
(`clients.conf`, `proxy.conf`, `radiusd.conf`) and compose / `.env`
bundles that ship a default or well-known shared secret on a NAS or
home-server entry reachable from non-loopback peers.

RADIUS authenticates a NAS to the RADIUS server with a single
per-client shared secret. The secret is also used to obscure
`User-Password` (RFC 2865) and to compute the `Response Authenticator`.
A weak secret therefore (a) lets anyone who can spoof a NAS source
address inject Access-Request / Accounting-Request packets, and
(b) lets a passive observer recover user passwords offline.

The defaults shipped in vendor docs and tutorials -- `testing123`,
`secret`, `radius`, `changeme`, `password`, `admin` -- are the first
strings every scanner tries. LLMs asked "give me a working
clients.conf" routinely emit `secret = testing123` because that is
what the FreeRADIUS upstream sample uses.

## Why LLMs emit this

* The upstream FreeRADIUS sample `clients.conf` ships
  `secret = testing123` for the `localhost` entry and most
  copy-pasted tutorials forget to change it before adding a
  non-loopback `client` block.
* "Test your RADIUS server with `radclient`" walkthroughs all
  use `testing123`.
* Compose stacks for captive-portal / hotspot demos hard-code
  `RADIUS_SECRET=secret` or `RADIUS_SECRET=changeme`.

## What it catches

Per file (line-level):

- `secret = testing123` / `secret=testing123` and other well-known
  defaults inside any `client { ... }` block, or top-level in a
  `clients.conf`-shape file.
- `secret = "<weak>"` quoted form.
- The same on `home_server { ... }` (proxy) blocks.
- Env-var assignments shipped in compose / `.env` shape:
  `RADIUS_SECRET=<weak>`, `FREERADIUS_SECRET=<weak>`,
  `RADIUS_CLIENT_SECRET=<weak>`, `RADSEC_SECRET=<weak>`.

Per file (whole-file):

- `clients.conf`-shape file with a `client { ... }` block whose
  `ipaddr` is non-loopback **and** no `secret` line at all.

## What it does NOT catch

- `secret = ...` whose value is >= 22 chars and contains both a
  digit and a non-alphanumeric (treated as "not a default").
- `client localhost { ipaddr = 127.0.0.1; secret = testing123 }`
  -- loopback-only NAS blocks.
- Lines marked with trailing `# radius-default-ok`.
- Files containing `# radius-default-ok-file` anywhere.
- Blocks bracketed by `# radius-default-ok-begin` /
  `# radius-default-ok-end`.

## Usage

```
python3 detector.py <file_or_dir> [...]
```

Exit code = number of files with at least one finding (capped at 255).
Stdout lines = `<file>:<line>:<reason>`.

## Verify

```
bash verify.sh
```

Expected: `bad=N/N good=0/M PASS`.

## Refs

- CWE-521 Weak Password Requirements
- CWE-798 Use of Hard-coded Credentials
- CWE-1188 Insecure Default Initialization of Resource
- RFC 2865 s.3 -- shared-secret usage and selection guidance
