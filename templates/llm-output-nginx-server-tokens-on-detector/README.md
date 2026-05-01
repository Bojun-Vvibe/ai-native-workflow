# llm-output-nginx-server-tokens-on-detector

Static lint that flags nginx configuration files which leak the
nginx version in the ``Server`` response header — either by
explicitly setting ``server_tokens on;`` or by silently relying on
the leaky default.

## Why LLMs emit this

Nginx's default behaviour is to send::

    Server: nginx/1.25.3

…on every response and to print the same version on every
auto-generated error page. The fix is one line:

```nginx
http {
    server_tokens off;
}
```

But that one line is missing from the default ``nginx.conf``
shipped by every distro, missing from the official "Beginner's
Guide" example, and missing from ~all "set up nginx as a reverse
proxy" tutorials. So LLMs trained on those samples emit configs
that simply forget about it. A smaller-but-louder failure mode is
when the model copies "show me every nginx directive" examples
that include ``server_tokens on;`` explicitly.

The leaked version is the single most useful piece of recon for
attacker tooling — it pins down the exact CVE list, the exact set
of off-by-one parser quirks, and the exact module ABI to target.

## What it catches

Per file, line-level findings:

- `server_tokens on;`
- `server_tokens build;` (also leaks build name)

Per file, whole-file finding:

- The file contains an `http {` block AND no `server_tokens off;`
  AND no `more_clear_headers Server;` / `more_set_headers 'Server:
  ...';` (the `ngx_http_headers_more` module's masking
  directives)

## What it does NOT flag

- `server_tokens off;`
- Files that mask via `more_clear_headers Server;` or
  `more_set_headers 'Server: ...';`
- Pure `stream {}` TCP-LB configs, `mail {}` configs, or included
  fragments without their own `http {` block
- Lines with a trailing `# ngx-tokens-ok` comment
- Files containing `ngx-tokens-ok-file` anywhere

## How to detect

```sh
python3 detector.py path/to/nginx-config-dir/
```

Exit code = number of files with a finding (capped 255). Stdout:
`<file>:<line>:<reason>`.

## Safe pattern

```nginx
http {
    server_tokens off;

    server {
        listen 443 ssl http2;
        server_name app.example.com;
        ...
    }
}
```

Or, if you want to drop the header entirely (requires the
`ngx_http_headers_more` module):

```nginx
http {
    more_clear_headers Server;
    ...
}
```

## Refs

- CWE-200: Exposure of Sensitive Information to an Unauthorized
  Actor
- CWE-209: Generation of Error Message Containing Sensitive
  Information
- OWASP ASVS v4 §14.3.2 — HTTP banner / version disclosure
- nginx docs: `server_tokens` directive
- nginx docs: `ngx_http_headers_more` module

## Verify

```sh
bash verify.sh
```

Should print `bad=4/4 good=0/3 PASS`.
