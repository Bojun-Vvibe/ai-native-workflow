# llm-output-pihole-webpassword-empty-detector

Detect Pi-hole `setupVars.conf` snippets that LLMs commonly emit
with the admin Web UI password (`WEBPASSWORD`) left empty,
missing on a configured install, or set to an obvious
placeholder. Pi-hole's admin UI gates query-log access, blocklist
edits, custom DNS / CNAME records, and `dnsmasq` config writes
behind WEBPASSWORD; an empty value disables the login screen
entirely so any host that can reach the admin port (default 80)
gets full DNS-rewriter privileges over every client that uses
this Pi-hole as a resolver.

When asked "give me a setupVars.conf for my Pi-hole container"
or "make Pi-hole start without prompting for a password", models
routinely:

- Render `WEBPASSWORD=` on its own line because the installer
  emits that shape when you skip the prompt.
- Render `WEBPASSWORD=""` "to show that it is empty on purpose".
- Render `WEBPASSWORD=CHANGEME` (or `TODO`, `<set-this>`,
  `password`, `admin`) and ship the file as-is.
- Omit the `WEBPASSWORD` line entirely while still defining
  `PIHOLE_INTERFACE`, `IPV4_ADDRESS`, and `BLOCKING_ENABLED`,
  matching the "I just installed and skipped the password
  prompt" shape.

## Bad patterns

1. `WEBPASSWORD=` with nothing after the `=`.
2. `WEBPASSWORD=""` or `WEBPASSWORD=''`.
3. `WEBPASSWORD=<placeholder>` for placeholder ∈ {`CHANGEME`,
   `TODO`, `xxx`, `placeholder`, `replaceme`, `password`,
   `admin`, `pihole`, `yourpassword`, `yourpasswordhere`}.
4. A configured Pi-hole file (with `PIHOLE_INTERFACE` /
   `IPV4_ADDRESS` / `BLOCKING_ENABLED` / `PIHOLE_DNS_1` present)
   with no `WEBPASSWORD=` line at all.

## Good patterns

- `WEBPASSWORD=<64-hex doubled-SHA256 digest>` produced by
  `pihole -a -p`.
- `WEBPASSWORD="<plain passphrase>"` of length ≥ 8 that is not a
  placeholder (operators sometimes pre-seed before running
  `pihole -a -p`).
- A `setupVars.conf`-shaped file that only mentions
  `WEBPASSWORD` inside `#` comments.
- A non-Pi-hole file that happens to define `WEBPASSWORD=` for
  some unrelated tool (no Pi-hole install fingerprints in scope).

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-webpassword-empty.conf
BAD  samples/bad/02-webpassword-empty-quoted.conf
BAD  samples/bad/03-webpassword-placeholder.conf
BAD  samples/bad/04-webpassword-missing.conf
GOOD samples/good/01-webpassword-real-hash.conf
GOOD samples/good/02-doc-comment-only.conf
GOOD samples/good/03-webpassword-strong-quoted.conf
GOOD samples/good/04-not-setupvars.conf
bad=4/4 good=0/4 PASS
```

## Why this matters

Pi-hole sits between every device on a network and DNS. Whoever
controls the Pi-hole admin UI controls:

- Which domains resolve and which are sinkholed (so they can
  un-block ad / tracker / phishing domains for everyone behind
  the Pi-hole, or block legitimate domains).
- Custom A / AAAA / CNAME records (so they can point
  `mail.<your-domain>` or `git.<your-domain>` at an attacker box
  for credential capture).
- Upstream resolvers (so they can route every query through an
  attacker-controlled DNS server with logging).
- The query log itself, which leaks every domain every client
  has visited.

Pi-hole installer shipped a "password reset" footgun for years
(`pihole -a -p '' ` clears the password) and the documentation
explicitly warns that an empty WEBPASSWORD disables login. LLMs
trained on installer output and forum snippets reproduce the
empty-or-placeholder shape because it parses cleanly and the
admin UI starts up just fine.

The detector is deliberately narrow:

- Requires a Pi-hole install fingerprint (`PIHOLE_INTERFACE` /
  `IPV4_ADDRESS` / `BLOCKING_ENABLED` / `PIHOLE_DNS_1`). A bare
  `WEBPASSWORD=` in some unrelated env file does not fire.
- Strips `#` line comments before scanning so commented-out
  examples in templates do not false-fire.
- Accepts any non-placeholder string of length ≥ 8 as "looks
  real" — we do not try to validate that the value is actually a
  doubled-SHA256 digest, because operators legitimately seed
  plain passphrases.
- Does not fire on a file with no Pi-hole fingerprints, even if
  it contains `WEBPASSWORD=`.

Bash 3.2+ / awk / coreutils only. No network calls.
