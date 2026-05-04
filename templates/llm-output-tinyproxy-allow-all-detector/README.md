# llm-output-tinyproxy-allow-all-detector

Detects Tinyproxy configurations that turn the daemon into an open
forward HTTP proxy reachable from the internet — the shape that LLM
quickstart snippets emit when asked "give me a quick HTTP proxy I can
run on my VPS".

## Why this matters

Tinyproxy's default `tinyproxy.conf` ships with `Allow 127.0.0.1`
(and an unset or `0.0.0.0` `Listen`). The bind exists; the ACL is
the only thing stopping anyone on the internet from using the proxy
as an anonymizing relay.

Adding `Allow 0.0.0.0/0` (or `Allow 0/0`, or `Allow ::/0`) to that
config — the literal answer LLMs give when a user says "it's
refusing my requests, just allow everyone" — turns the host into:

* a credit-card-carding relay,
* a scraping-abuse cut-out (the abuse complaint lands on your IP),
* a reflection point for egress traffic that is hard to attribute
  back to the real source.

This detector flags the exact `(public Listen) + (Allow * ) + (no
BasicAuth)` triple.

## Rules

A finding is emitted when ALL three hold:

1. **Public listener.** `Listen` is unset (Tinyproxy default is to
   bind every interface), or `Listen` is `0.0.0.0`, `::`, `[::]`,
   or a routable IP / hostname. `Listen 127.0.0.1` / `Listen ::1`
   are treated as loopback-only and the file is *not* flagged.
2. **World-open ACL.** At least one `Allow` directive matches
   `0.0.0.0/0`, `0.0.0.0` (no mask), `0/0`, `::/0`, or `::`.
3. **No `BasicAuth`** directive is configured. (BasicAuth doesn't
   close the network exposure on its own, but it changes the threat
   model enough that we treat it as a separate finding.)

A line containing the marker `# tinyproxy-public-allowed`
suppresses the finding for the whole file (use this for
intentionally public proxies — e.g. lab honeypots, CDN edges with
external auth in front).

## Out of scope

* `BasicAuth`-protected proxies that are still bound publicly.
* Squid, 3proxy, Privoxy, HAProxy `mode http` forward configs.
  Other detectors in this chain cover Squid (`squid-http-access-
  allow-all`).

## Run

```
python3 detector.py examples/bad/01_default_listen_allow_all.conf
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.
