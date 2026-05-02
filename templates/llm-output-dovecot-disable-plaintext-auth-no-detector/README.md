# llm-output-dovecot-disable-plaintext-auth-no-detector

Static lint that flags Dovecot IMAP/POP3 configuration files that
allow PLAIN/LOGIN authentication over unencrypted connections —
either by setting `disable_plaintext_auth = no` outright, by
turning the SSL stack off (`ssl = no`) while still advertising
PLAIN/LOGIN auth mechanisms, or by failing to set
`ssl = required` on a top-level config that already weakens the
defaults.

## Why LLMs emit this

Dovecot's default `disable_plaintext_auth = yes` is one of the
unsung heroes of mail-server security: it refuses PLAIN and LOGIN
auth on a non-TLS connection, which is the only thing preventing
every shared-WiFi attacker on the network from trivially
harvesting mailbox credentials.

When a user pastes "Thunderbird won't log in to my Dovecot,
please fix" into an LLM, the most common single-line answer is:

```dovecot
disable_plaintext_auth = no
```

…which "fixes" the symptom by disabling the protection. A
sneakier failure mode is `ssl = no` plus PLAIN/LOGIN
`auth_mechanisms`, which leaves the default
`disable_plaintext_auth = yes` in place but eliminates TLS as a
gate, so plaintext is effectively the only path.

## What it catches

Per file, line-level findings:

- `disable_plaintext_auth = no`
- `ssl = no` on a file that also advertises PLAIN/LOGIN auth
  mechanisms

Per file, whole-file finding:

- The file looks like a top-level Dovecot server config (contains
  `protocols =`, `listen =`, `mail_location =`, or a
  `service imap-login` / `service pop3-login` block) AND it weakens
  the SSL/auth stack (either `ssl = no` or PLAIN/LOGIN
  `auth_mechanisms`) AND it does not explicitly set
  `disable_plaintext_auth = yes` and `ssl = required`.

## What it does NOT flag

- `disable_plaintext_auth = yes`
- `ssl = required`
- Pure include fragments that contain only `passdb` / `userdb` /
  `namespace` blocks and no top-level server-identity directives.
- Lines with a trailing `# dovecot-plain-ok` comment.
- Files containing `dovecot-plain-ok-file` anywhere.

## How to detect

```sh
python3 detector.py path/to/dovecot-config-dir/
```

Exit code = number of files with a finding (capped 255). Stdout:
`<file>:<line>:<reason>`.

## Safe pattern

```dovecot
protocols = imap pop3
listen = *, ::
mail_location = maildir:~/Maildir

ssl = required
ssl_cert = </etc/dovecot/cert.pem
ssl_key = </etc/dovecot/key.pem

disable_plaintext_auth = yes
auth_mechanisms = plain login

service imap-login {
    inet_listener imaps {
        port = 993
        ssl = yes
    }
}
```

## Refs

- CWE-319: Cleartext Transmission of Sensitive Information
- CWE-523: Unprotected Transport of Credentials
- OWASP ASVS v4 §9.1.1 — TLS for all auth surfaces
- Dovecot wiki — `disable_plaintext_auth`, `ssl`

## Verify

```sh
bash verify.sh
```

Should print `bad=4/4 good=0/3 PASS`.
