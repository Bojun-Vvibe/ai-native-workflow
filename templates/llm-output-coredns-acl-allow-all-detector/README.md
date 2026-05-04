# llm-output-coredns-acl-allow-all-detector

Detects CoreDNS `Corefile` configurations whose `acl` plugin grants
unrestricted query access to the world (`allow net 0.0.0.0/0` or
`allow net ::/0`) on a public listener — the exact shape that LLM
quickstart snippets emit when asked "how do I expose CoreDNS to the
internet" and that turns the resolver into an open recursive resolver
ready for DNS amplification abuse.

## Why this matters

CoreDNS by default does not gate queries by source IP. The `acl`
plugin exists to add that gate. A block of the form

```
.:53 {
    acl {
        allow net 0.0.0.0/0
    }
    forward . 1.1.1.1
    cache
}
```

binds the resolver to all interfaces (`.:53`) and explicitly opens
the ACL to every IPv4 address — i.e. the operator added the plugin,
spelled out the rule, and got the rule backwards. Open recursive
resolvers are routinely co-opted into reflection / amplification
DDoS campaigns; this is why `dnsflood` and `dns-amplification` show
up in network-abuse reports.

This detector flags that exact shape while leaving private-network
ACLs (`allow net 10.0.0.0/8`, `allow net 192.168.0.0/16`, etc.)
alone.

## Rules

For each server block in the Corefile:

1. The block header binds to a public host: empty host, `.`,
   `0.0.0.0`, `::`, or `[::]` (with an optional scheme like
   `dns://` / `tls://` / `grpc://` and an optional port).
2. The block contains an `acl { ... }` plugin block.
3. That plugin block contains at least one `allow net` directive
   matching `0.0.0.0/0` or `::/0`.
4. The plugin block does NOT contain an offsetting `block net` /
   `filter net` directive that also matches `0.0.0.0/0` or `::/0`
   (which would re-narrow the policy).

If all four hold, the block is flagged.

A line containing the marker `# coredns-public-resolver-allowed`
suppresses the finding for the whole file (use this for honeypots
and intentional public resolvers like Quad9 / Cloudflare clones).

## Scope / out of scope

* In scope: `Corefile` and `*.conf` files that follow Corefile syntax.
* Out of scope: Kubernetes `ConfigMap` YAML wrappers (the inner
  Corefile is still scanned if it is the file passed in directly).
* Out of scope: query rate limiting via the `ratelimit` or `rrl`
  plugins — those mitigate but do not replace an ACL.

## Run

```
python3 detector.py examples/bad/01_default_acl_open.corefile
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.
