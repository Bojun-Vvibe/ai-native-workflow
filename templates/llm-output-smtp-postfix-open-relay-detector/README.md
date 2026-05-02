# llm-output-smtp-postfix-open-relay-detector

Detects Postfix `main.cf` files whose relay-control directives form a
classic **open mail relay** — a configuration that lets any internet
client submit mail with arbitrary `From:` and `To:` envelopes.

## Why this matters

An open relay is one of the oldest and most punishing
misconfigurations on the internet. Within hours of being discovered,
a relay will be saturated by spam and phishing campaigns, causing the
hosting IP (and often the entire /24) to land on RBLs (Spamhaus,
SORBS, Barracuda) for weeks. Recovery requires manual delisting per
RBL plus reputation rebuild.

LLM-generated `main.cf` examples frequently hit this pattern because
they cargo-cult permissive `mynetworks` and `smtpd_relay_restrictions`
to "just make it work":

    mynetworks = 0.0.0.0/0
    smtpd_relay_restrictions = permit
    smtpd_recipient_restrictions = permit

The detector flags those shapes.

## What it detects

For each scanned `main.cf`, the detector reports a finding when **any**
of the following independently insecure conditions is observed:

1. `mynetworks` includes `0.0.0.0/0`, `::/0`, or any IPv4 address with
   a `/0` through `/7` prefix length (treats the entire internet as a
   trusted submission source).
2. `smtpd_relay_restrictions` resolves to `permit` (or starts with
   `permit` before any `reject_unauth_destination` clause).
3. `smtpd_recipient_restrictions` is missing
   `reject_unauth_destination` AND does not include
   `reject_unauth_pipelining` / `reject_unauth_destination` style
   guards before its terminating `permit`.
4. `relay_domains` is set to a wildcard (`*`) or to a list including
   the literal `$mydomain` together with `mynetworks = 0.0.0.0/0`.

Each finding cites the offending line.

## CWE references

- CWE-732: Incorrect Permission Assignment for Critical Resource
- CWE-284: Improper Access Control
- CWE-693: Protection Mechanism Failure

## False-positive surface

- Authoritative outbound-only relays for a closed VPN may legitimately
  include very wide `mynetworks`. Suppress per file with a top
  comment `# smtp-open-relay-allowed`.
- Configs that use `smtpd_sender_restrictions` with SASL
  (`permit_sasl_authenticated`) before any wide `permit` are treated
  as authenticated.

## Usage

    python3 detector.py path/to/main.cf

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
