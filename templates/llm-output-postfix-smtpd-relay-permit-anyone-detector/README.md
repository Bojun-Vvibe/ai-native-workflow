# llm-output-postfix-smtpd-relay-permit-anyone-detector

Detects Postfix `main.cf` configurations whose `smtpd_relay_restrictions`
(or, on legacy versions, `smtpd_recipient_restrictions`) effectively turn
the MTA into an **open relay** by listing `permit` (the catch-all
allow rule) before — or instead of — any `reject_unauth_destination`
clause.

## Why this matters

Postfix evaluates restriction lists left-to-right. The very first
`permit` (or `permit_auth_destination`-equivalent catch-all) wins for
that connection. The standard, safe shape is to put restrictive
predicates first and finish with `reject_unauth_destination`:

```
smtpd_relay_restrictions =
    permit_mynetworks
    permit_sasl_authenticated
    reject_unauth_destination
```

LLM-generated configs frequently regress to one of:

```
smtpd_relay_restrictions = permit
```

```
smtpd_relay_restrictions =
    permit_mynetworks
    permit
    reject_unauth_destination
```

```
smtpd_recipient_restrictions = permit_mynetworks, permit, reject_unauth_destination
```

All three accept mail destined for *any* domain from *any* peer ⇒
the host becomes spam-relay infrastructure within minutes of being
network-reachable on TCP/25.

## What's checked

For each parameter line whose key is `smtpd_relay_restrictions` or
`smtpd_recipient_restrictions` (including comma- and continuation-
line value lists), the detector flags the file when:

1. A bare `permit` token appears in the value list (with no
   suffix — `permit_mynetworks`, `permit_sasl_authenticated`,
   `permit_auth_destination`, `permit_tls_clientcerts` are *not*
   the catch-all and are ignored), AND
2. There is no `reject_unauth_destination` token positioned
   *before* the bare `permit`.

Continuation lines (RFC-style indented continuations and the
Postfix `\\`-newline form) are folded before tokenization. Comments
(`#...` to end of line) are stripped.

## Accepted (not flagged)

- Standard safe form ending in `reject_unauth_destination`.
- Files containing the comment `# postfix-open-relay-allowed`
  (intentional honeypot / lab fixtures).
- Parameters other than the two relay-control names.

## Refs

- CWE-269: Improper Privilege Management
- CWE-732: Incorrect Permission Assignment for Critical Resource
- Postfix `SMTPD_ACCESS_README` — restriction evaluation order

## Usage

```
python3 detector.py path/to/main.cf [more.cf ...]
```

Exit code = number of flagged files (capped at 255). Findings are
printed as `<file>:<line>:<reason>`.
