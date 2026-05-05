# llm-output-nextcloud-trusted-domains-wildcard-detector

Detect Nextcloud `config.php` snippets where the `trusted_domains` array
contains a wildcard entry — `'*'`, an inner-`*` glob like `*.example.com`,
or the bind-everything sentinel `'0.0.0.0'`.

Nextcloud uses `trusted_domains` as a strict host-header allowlist. The
server compares the incoming `Host:` header against each entry; only
matching hosts are allowed to serve the UI and OAuth/password-reset
flows. If any entry effectively matches every hostname:

- An attacker can serve the instance under an attacker-controlled
  hostname (e.g. by spoofing DNS on a LAN, or by routing
  `attacker.com` at the public IP).
- Password-reset emails and OAuth `redirect_uri` callbacks are
  generated using the request `Host:`, so the attacker receives the
  reset link / OAuth code.
- Web-cache poisoning becomes possible because every Host variant is
  treated as canonical.

LLMs frequently emit `'*'` "to make it work behind the reverse proxy"
when a tutorial complains about an "untrusted domain" warning. The
correct fix is to enumerate the real public/internal hostnames.

## What bad LLM output looks like

Pure wildcard:

```php
'trusted_domains' => array(0 => '*'),
```

Glob wildcard:

```php
'trusted_domains' => ['cloud.example.com', '*.example.com'],
```

Bind-everything sentinel pasted as a hostname:

```php
'trusted_domains' => ['cloud.internal', '0.0.0.0'],
```

## What good LLM output looks like

```php
'trusted_domains' => array(
  0 => 'cloud.example.com',
  1 => 'cloud.internal.example.com',
),
```

Specific IPs (e.g. `10.0.0.5`) are accepted because they are not
wildcards — they only allow that exact host header.

A file that does not contain a `trusted_domains` key at all is not
considered a Nextcloud config and is not flagged — see
`samples/good-3.txt`.

## How the detector decides

1. Find a `'trusted_domains'` PHP array assignment (`=>`). If absent,
   the file is not a Nextcloud config; do not flag.
2. Track array bracket depth (`[ ]` and `array(...)`) so the value is
   inspected even when it spans multiple lines.
3. For every quoted string element inside that value, flag the file
   if any element is `*`, contains an unescaped `*`, or is the literal
   `0.0.0.0`.

## Run the worked example

```sh
bash run-tests.sh
```

Expected output:

```
bad=4/4 good=0/4 PASS
```

The four bad fixtures cover: pure `'*'`, `*.example.com` glob,
`'0.0.0.0'` sentinel, and a trailing-`*` glob (`backup.*`). The four
good fixtures cover: enumerated hostnames, single FQDN, an unrelated
config that happens to contain `'*'` elsewhere, and a mix of FQDN
plus specific private IPs.

## Run against your own files

```sh
bash detect.sh path/to/config.php path/to/another/config.php
# or via stdin:
cat config.php | bash detect.sh
```

Exit code is `0` only if every `bad-*` sample is flagged and no
`good-*` sample is flagged, so this is safe to wire into CI as a
defensive misconfiguration gate for Nextcloud deployments.
