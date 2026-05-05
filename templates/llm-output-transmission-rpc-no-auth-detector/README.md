# llm-output-transmission-rpc-no-auth-detector

Stdlib-only Python detector that flags **Transmission** BitTorrent
daemon configurations which disable RPC authentication, or which
combine a disabled IP whitelist with a public RPC bind. Maps to
**CWE-306** (missing authentication for critical function),
**CWE-1188** (insecure default initialization of resource), and
**CWE-284** (improper access control).

Transmission's RPC interface (the same one the web UI and `transmission-
remote` CLI talk to) can add torrents, change the `download-dir`
(which makes the daemon write attacker-controlled bytes anywhere it
has filesystem permission), and execute the script configured under
`script-torrent-done-filename`. An unauthenticated RPC reachable on
a routable interface is therefore a remote code execution primitive,
not just a "anyone can pause my downloads" annoyance.

LLMs reach for `"rpc-authentication-required": false` because it is
the standard one-line "fix" for the user-facing error `409: Conflict`
or for the web UI prompting for a username/password the developer
does not remember setting. The change ships in a Helm chart, the pod
binds `0.0.0.0:9091`, and the cluster is one port-scan away from
unauthenticated torrent-driven file write.

## Heuristic

We flag any of the following, outside `#` / `;` / `//` comment lines:

1. `"rpc-authentication-required": false` directive in
   `settings.json` (any spacing, optional trailing comma).
2. `"rpc-whitelist-enabled": false` directive paired with
   `"rpc-bind-address": "0.0.0.0"` or `"::"` in the same file (the
   IP whitelist is the only fallback access control once auth is on
   the default password — disabling it on a public bind removes that
   fallback).
3. `transmission-daemon -T` or `transmission-daemon --no-auth` on a
   command line (Dockerfile CMD/ENTRYPOINT, shell wrapper, systemd
   `ExecStart`, k8s `args`).
4. Environment-variable override
   `TRANSMISSION_RPC_AUTHENTICATION_REQUIRED=false` (used by
   `linuxserver/transmission`, `haugene/transmission-openvpn`, and
   similar templated container images).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-284**: Improper Access Control.
- Transmission `settings.json` reference: `rpc-authentication-
  required` defaults to `true`; the `rpc-whitelist` defaults to
  `127.0.0.1` so a developer who flips it to `0.0.0.0` for "remote
  access" must also keep auth on, not turn both off.

## What we accept (no false positive)

- `"rpc-authentication-required": true` (the default).
- `"rpc-whitelist-enabled": false` with a localhost / private bind
  (`127.0.0.1`, `::1`, or any RFC1918 address) — we only fire on
  the combination with `0.0.0.0` / `::`.
- Commented-out lines (`// "rpc-authentication-required": false`,
  `# TRANSMISSION_RPC_AUTHENTICATION_REQUIRED=false`).
- Documentation / Markdown mentions (we only scan config-shaped
  files).
- Other RPC keys that happen to share the prefix
  (`rpc-authentication-required-v2`, `rpc-username`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       4 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/settings.json
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

Disabling RPC auth is the canonical Stack Overflow answer to "I get
a `409: Conflict` from Transmission" or "the web UI keeps asking for
a password I never set". An LLM trained on those threads will offer
`"rpc-authentication-required": false` as a one-line fix. The
developer accepts, the `settings.json` is templated into a Helm
chart, and the daemon ships exposed. The detector exists to catch
the paste before it ships.
