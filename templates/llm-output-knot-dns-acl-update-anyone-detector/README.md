# llm-output-knot-dns-acl-update-anyone-detector

Detect Knot DNS server configurations that LLMs commonly emit with
an `acl:` entry permitting the RFC 2136 dynamic-update action from
any source address. Knot DNS uses a YAML-style configuration. An
ACL list element that grants `action: update` AND either omits
`address:` or sets it to `0.0.0.0/0` / `::/0` / the bareword `any`
lets anyone on the internet rewrite the zone — equivalent to
publishing the zone signing key.

When asked "give me a Knot DNS config that supports nsupdate" or
"set up dynamic DNS for my home network", models routinely:

- Drop in an `acl:` element with `action: update` and forget the
  `address:` key entirely. Knot then matches every source.
- Write `address: 0.0.0.0/0` because the model generalised from
  "match anywhere" examples, not noticing that `update` is the one
  action where this is catastrophic.
- Use the plural `actions:` spelling that older Knot docs
  accepted, hiding the rule from naive `grep "action:"` scans.
- Use the `address: any` shortcut from example templates.

## Bad patterns

1. `acl:` list element with `action: update` and **no** `address:`
   key in the same element.
2. `acl:` list element with `action: update` (or `actions:
   [..., update, ...]`) and `address: 0.0.0.0/0`.
3. Same shape with `address: ::/0` (IPv6 catch-all).
4. Same shape with `address: any` (bareword).

## Good patterns

- `acl:` element with `action: update` and a concrete non-default
  CIDR (e.g. `10.0.0.0/8`, `192.0.2.7/32`).
- `acl:` element that grants only `transfer` and/or `notify` —
  read-only or signalling actions, never zone rewrite.
- `acl:` elements that omit the `update` action entirely.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-update-no-address.conf
BAD  samples/bad/02-update-zero-cidr.conf
BAD  samples/bad/03-actions-list-v6-any.conf
BAD  samples/bad/04-address-any-keyword.conf
GOOD samples/good/01-update-rfc1918.conf
GOOD samples/good/02-transfer-notify-only.conf
GOOD samples/good/03-no-update-action.conf
GOOD samples/good/04-update-host-cidr.conf
bad=4/4 good=0/4 PASS
```

## Why this matters

RFC 2136 dynamic updates are the legitimate way for DHCP servers,
provisioning systems, and ACME challenge runners to add records to
a zone at runtime. The action is unauthenticated at the DNS layer —
authentication relies entirely on either the network ACL
(`address:`) or a TSIG `key:` reference. When an LLM-generated
config grants `update` from `0.0.0.0/0`, every record in the zone
is writable by every host on the internet: an attacker can rewrite
`A`, `MX`, `TXT` (including ACME challenge records, which lets
them mint TLS certificates for the domain), or `NS` records and
take over the domain.

The detector is deliberately narrow:

- It only fires on ACL elements that actually grant `update`. A
  `transfer`-only or `notify`-only ACL with `address: 0.0.0.0/0`
  is not flagged — that pattern leaks zone contents but does not
  permit zone rewrite, which is a different (and much weaker)
  threat.
- It accepts both `action:` and `actions:` spellings, and both
  scalar (`action: update`) and sequence (`action: [transfer,
  update]`) forms.
- It strips `#` line comments so that documentation that quotes
  the bad pattern inside a comment doesn't false-fire.
- It requires a recognisable Knot YAML shape (`acl:` block plus
  another known top-level section, or list items with `id:` keys)
  before scanning, so that arbitrary YAML files in the same
  repository don't get matched by accident.

Bash 3.2+ / awk / coreutils only. No network calls.
