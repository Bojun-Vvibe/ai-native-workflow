# llm-output-apache-serversignature-on-detector

Static lint that flags Apache httpd configuration files which leak
the server identity by enabling `ServerSignature`, by leaving
`ServerTokens` at the verbose default `Full` level, or by simply
forgetting to set either directive on a top-level config.

## Why LLMs emit this

Apache httpd's defaults are leaky:

```
Server: Apache/2.4.58 (Ubuntu) OpenSSL/3.0.13 mod_wsgi/4.9.4
```

…on every response, plus the same string at the bottom of every
auto-generated error page when `ServerSignature On` (or `EMail`)
is set. The fix is two lines:

```apache
ServerTokens Prod
ServerSignature Off
```

But neither line appears in the canonical `httpd.conf` shipped by
most distros, neither line appears in the official "Getting
Started" guide, and neither line appears in ~all "set up Apache as
a reverse proxy" tutorials. So LLMs trained on those samples emit
configs that simply forget about it. A louder failure mode is when
the model copies "show me every Apache directive" examples and
emits `ServerSignature On` or `ServerTokens Full` explicitly.

The leaked version + module list is the single most useful piece
of recon for attacker tooling — it pins down the exact CVE list
and module ABI to target.

## What it catches

Per file, line-level findings:

- `ServerSignature On`
- `ServerSignature EMail`
- `ServerTokens Full`
- `ServerTokens OS`
- `ServerTokens Major` / `Minor` / `Min`

Per file, whole-file finding:

- The file looks like a top-level Apache server config (contains
  `Listen`, `<VirtualHost`, `ServerName`, or `DocumentRoot`) AND
  it is missing `ServerSignature Off` AND/OR `ServerTokens Prod`
  (or `ProductOnly`).

## What it does NOT flag

- `ServerSignature Off`
- `ServerTokens Prod` / `ProductOnly`
- Pure include fragments that only contain `<Directory>` /
  `<Location>` / `Alias` rules and no top-level server directives
- Lines with a trailing `# httpd-sig-ok` comment
- Files containing `httpd-sig-ok-file` anywhere

## How to detect

```sh
python3 detector.py path/to/apache-config-dir/
```

Exit code = number of files with a finding (capped 255). Stdout:
`<file>:<line>:<reason>`.

## Safe pattern

```apache
Listen 443
ServerName secure.example.com
DocumentRoot "/srv/secure"

ServerTokens Prod
ServerSignature Off

<VirtualHost *:443>
    ServerName secure.example.com
    SSLEngine on
</VirtualHost>
```

## Refs

- CWE-200: Exposure of Sensitive Information to an Unauthorized
  Actor
- CWE-209: Generation of Error Message Containing Sensitive
  Information
- OWASP ASVS v4 §14.3.2 — HTTP banner / version disclosure
- Apache httpd docs: `ServerSignature` directive
- Apache httpd docs: `ServerTokens` directive

## Verify

```sh
bash verify.sh
```

Should print `bad=4/4 good=0/3 PASS`.
