# llm-output-squid-http-access-allow-all-detector

## Problem

When an LLM scaffolds a Squid proxy configuration, it often writes a top-level
`http_access allow all` rule (or `http_access allow !whatever ... allow all`
catch-all) without first restricting `acl localnet` / `acl SSL_ports` / source
networks. The result is an **open forward proxy** reachable from the public
internet — abused for credential stuffing, scraping, ad-fraud, and lateral
pivoting through corporate egress.

The official Squid default config explicitly comments:

```
# Recommended minimum Access Permission configuration:
#
# Deny requests to certain unsafe ports
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
#
# Only allow cachemgr access from localhost
http_access allow localhost manager
http_access deny manager
#
# We strongly recommend the following be uncommented to protect innocent
# web applications running on the proxy server who think the only
# one who can access services on "localhost" is a local user
http_access deny to_localhost
#
# Example rule allowing access from your local networks.
# Adjust localnet in the ACLs section to list your (internal) IP networks
# from where browsing should be allowed
http_access allow localnet
http_access allow localhost
#
# And finally deny all other access to this proxy
http_access deny all
```

A `http_access allow all` line — uncommented, at file scope, not gated by an
`acl` that restricts to `localnet`/`localhost`/an authenticated group — flips
the deny-by-default posture and exposes the proxy.

## Why a detector

This is a single-line, syntactically obvious misconfig that LLM-generated infra
templates routinely produce when asked to "make a simple squid proxy that
works." Catching it at PR-review / pre-commit time prevents shipping an open
relay.

## Detection rule

Flag any line in a Squid `*.conf` (or fenced ```` ```squid ```` /
```` ```conf ```` block in markdown) where the directive is `http_access allow`
and the matching ACL token is the literal `all`, **unless** the same line also
contains a restricting ACL after `all` (Squid AND-joins ACLs on one line).

Specifically:
- Strip leading whitespace.
- Skip lines starting with `#`.
- Tokenize on whitespace.
- A line matches when:
  - `tokens[0] == "http_access"`
  - `tokens[1] == "allow"`
  - `"all"` appears in `tokens[2:]`
  - AND no token after `all` looks like a restrictor (`localnet`, `localhost`,
    `auth`, `authenticated`, `office_net`, etc.) — i.e. `all` is the *only*
    ACL on the line, OR the only ACLs after it are recognised wide-open
    pseudo-ACLs.

## Usage

```
python3 detector.py path/to/squid.conf [more.conf ...]
```

Exit code is the number of files that contain at least one finding. Findings
are printed as `path:line: <line>` to stdout.

Run the bundled fixtures:

```
./test.sh
```

Expected: `4/4` bad fixtures flag, `0/3` good fixtures flag, script exits 0.

## Limitations

- Does not parse `include` directives.
- Does not model `acl` redefinitions; if a user re-defines `all` to something
  narrow (Squid actually rejects this), the detector still flags. That is
  intentional — the literal `all` token is a code smell regardless.
- Markdown fence parsing is best-effort: only fenced blocks tagged `squid`,
  `conf`, or `squid.conf` are scanned.
