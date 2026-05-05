# llm-output-apache-mod-status-public-detector

Detects Apache `httpd` virtual host / server configuration that wires
`SetHandler server-status` (or `server-info`) inside a `<Location>`
block with no effective access restriction, leaving the
`/server-status` page reachable from any client.

## Why this matters

`mod_status` exposes a continuously updated dashboard of every active
HTTP request being served, including:

- request line (URL + query string),
- remote client IP,
- vhost being served,
- worker process state and CPU time,
- with `ExtendedStatus On` and `?refresh=N`, a near-realtime stream.

When this page is reachable without auth or IP allowlisting it is a
direct disclosure of authenticated session URLs (think
`?token=…`, `?reset_password=…`), internal-only paths, and request
volumes — useful for both targeted exploitation and reconnaissance.

LLM-generated httpd snippets routinely produce shapes like:

```apache
<Location /server-status>
    SetHandler server-status
</Location>
```

with no `Require` / `Allow from` / `AuthType` line at all, because
that's the snippet visible in many old how-tos. The detector flags
that shape so the LLM caller can intercept it before the config lands
in a real deployment.

## What it detects

For each scanned file, the detector parses `<Location>` and
`<LocationMatch>` blocks and reports a finding when **all** of:

1. The block contains `SetHandler server-status` or
   `SetHandler server-info`.
2. The block has none of:
   - a `Require` directive other than a public catch-all
     (`Require all granted`),
   - an `Allow from <token>` where every token is something other
     than `all`,
   - an `AuthType` / `AuthUserFile` pair,
   - a `Deny from all` baseline.
3. The block is not preceded by a file-level
   `# server-status-public-allowed` suppression marker.

A `Require all granted` with nothing else is treated as **public**
(that is the entire point of the directive). Loopback / private
allowlists (`Require ip 127.0.0.1`, `Allow from 10.0.0.0/8`) are
treated as restrictions.

## CWE references

- CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource

## False-positive surface

- Internal-only ops dashboards intentionally exposed on a private
  network. Suppress per file with a top comment
  `# server-status-public-allowed`.
- Status handlers wired up with `Require valid-user` or
  `Require ip 10.0.0.0/8` are NOT flagged.
- The detector does not parse `Include` / `IncludeOptional`
  fan-outs; restrictions defined in a separate file are not seen.

## Usage

    python3 detector.py path/to/httpd.conf

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
