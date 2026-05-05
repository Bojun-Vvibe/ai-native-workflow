# llm-output-bird-bgp-no-md5-password-detector

Detects BIRD Internet Routing Daemon configurations where a `protocol bgp`
block defines a `neighbor` peer but does not declare a `password "..."`
line — i.e. a BGP session without TCP-MD5 (RFC 2385) authentication.

## What it flags

For each `protocol bgp <name> { ... }` block that contains a `neighbor`
directive, the detector requires a `password` line inside the same block
(or inside a referenced `template bgp` block, when the block uses
`from <template>`). If neither is present the block is reported.

## Why it's bad

BGP runs over plain TCP. Without TCP-MD5 (or the newer TCP-AO) an
on-path attacker — or anyone who can spoof the peer's source address
and guess/observe the TCP sequence numbers — can inject UPDATE messages
or RST the session. For private peerings, IXP sessions and any
non-loopback iBGP this is the long-standing baseline hardening
recommendation.

The risk is amplified when the operator also disables TTL security
(no `ttl security`) and binds to a public interface, but the absence
of MD5 alone is enough to flag the config for review.

## References

- BIRD User's Guide, "Protocol BGP" — `password` option
  <https://bird.network.cz/?get_doc&v=20&f=bird-6.html#ss6.3>
- RFC 2385 — Protection of BGP Sessions via the TCP MD5 Signature Option
- RFC 5925 — TCP Authentication Option (TCP-AO), the modern successor
- NIST SP 800-189 §4.1 — BGP session integrity recommendations

## Usage

```
./detect.sh path/to/bird.conf
cat bird.conf | ./detect.sh -
```

Exit status:
- `0` — no insecure BGP block found
- `1` — at least one BGP block missing `password`; offending block
  header(s) printed to stdout with `file:line` location
- `2` — usage error

## Limitations

- Only inspects the file given on the command line; it does not follow
  `include "..."` directives.
- A `template bgp` that itself omits `password` will be flagged when it
  contains an inline `neighbor`; templates without `neighbor` are
  ignored (they cannot start a session on their own).
- A `protocol bgp X from Y { ... }` block satisfies the check if `Y`
  (or any ancestor template in the `from` chain inside the same file)
  declares a `password`.
- Comments (`#`, `//`, and `/* ... */`) are stripped before parsing so
  commented-out `password` lines do not falsely satisfy the check.
