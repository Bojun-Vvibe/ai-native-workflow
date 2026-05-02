# llm-output-nginx-ssl-protocols-tlsv1-detector

Detects nginx (and nginx-syntax) configuration files that enable
deprecated TLS protocol versions — `SSLv2`, `SSLv3`, `TLSv1`, or
`TLSv1.1` — on a `listen ... ssl` server block via the `ssl_protocols`
directive.

## Why this matters

TLS 1.0 and 1.1 were formally deprecated by the IETF in
[RFC 8996](https://datatracker.ietf.org/doc/html/rfc8996) (March 2021).
All major browsers removed support in 2020. SSLv2/SSLv3 have been
trivially broken since POODLE (2014). A server that still negotiates
these protocols downgrade-attacks any client that supports them and
fails every modern compliance baseline (PCI DSS 3.2.1+, NIST SP
800-52r2, BSI TR-02102-2).

LLM autocompletes for nginx TLS configuration regularly emit lines like:

    ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3;

— either copy-pasted from a 2016 blog post, or because the model is
optimizing for "compatibility" without knowing that the listed clients
no longer exist. This detector flags that shape so the LLM caller can
strip the legacy protocols before the config is offered for review.

## What it detects

For each scanned file the detector parses `ssl_protocols` directives
that appear inside (or above) a `server { ... }` block that itself has
at least one `listen ... ssl` (or `listen ... quic`) directive, and
reports a finding when the directive enables any of:

- `SSLv2`
- `SSLv3`
- `TLSv1` (i.e. TLS 1.0)
- `TLSv1.1`

If the directive only lists `TLSv1.2` and/or `TLSv1.3`, no finding is
emitted. The directive may also live in the surrounding `http { ... }`
block; in that case the finding line points at the `ssl_protocols`
directive itself.

A finding is suppressed for any directive whose line carries the
trailing comment marker `# llm-tls-legacy-ok` (escape hatch for
intentional legacy-client gateways behind a separate firewall).

## What it does NOT detect

- Missing `ssl_protocols` directive entirely. The default in nginx
  ≥ 1.23 is `TLSv1 TLSv1.1 TLSv1.2 TLSv1.3`, which is also unsafe, but
  flagging absence creates too much noise on partial snippets that
  rely on an outer `http {}`. Use a separate sibling detector for
  that policy if needed.
- `ssl_ciphers` weaknesses (RC4, DES, EXPORT). Covered by other
  detectors in this family.
- Apache / HAProxy / Envoy TLS configuration (different syntax).

## How to fix

```nginx
server {
    listen 443 ssl http2;
    server_name example.test;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    # ...
}
```

For a TLS-1.3-only deployment (recommended where the client base
allows it):

```nginx
ssl_protocols TLSv1.3;
```

## Usage

```
python3 detector.py path/to/nginx.conf
python3 detector.py path/to/conf.d/
bash verify.sh
```

Exit code is the number of files with at least one finding (capped at
255). Stdout lines have the form `<file>:<line>:<reason>`.
