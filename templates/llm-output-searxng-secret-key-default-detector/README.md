# llm-output-searxng-secret-key-default-detector

Detects SearXNG (`settings.yml`) and SearXNG-compose deployments where
`server.secret_key` is left at the upstream default `ultrasecretkey`,
or one of the well-known weak placeholder values shipped in tutorials
(`changeme`, `secret`, `replaceme`, `please_change_me`, an empty
string, or a literal sequence of `x`, `0`, or `a`).

## What it flags

The detector looks for two surfaces:

1. YAML form inside `settings.yml`:
   ```yaml
   server:
     secret_key: "ultrasecretkey"
   ```
   The key may be at the top level (`server.secret_key`) or appear as
   a bare `secret_key:` line within a `server:` block. Indentation is
   not enforced — the detector treats the file line-oriented.

2. Env / docker-compose form:
   ```
   SEARXNG_SECRET=ultrasecretkey
   SEARXNG_SECRET_KEY=changeme
   ```
   Both `SEARXNG_SECRET` and `SEARXNG_SECRET_KEY` are recognized,
   matching the names used by the upstream `searxng/searxng-docker`
   compose template across versions.

Comments after `#` (outside quoted strings) are stripped before
matching, so a stale commented-out default does not trigger the rule.

## Why it's bad

`server.secret_key` is the HMAC key SearXNG uses to:

- Sign the `image_proxy` URLs it generates so that an attacker cannot
  turn the instance into an open image-fetch proxy for arbitrary URLs.
- Sign anti-CSRF tokens on the preferences and search forms.
- (depending on version) seed the morty proxy URL signature.

If the key is the upstream default `ultrasecretkey` — which is
verbatim what the docs show and what countless tutorial copies still
contain — any attacker can:

- Forge `image_proxy` URLs and make the SearXNG host fetch arbitrary
  internal/external URLs (SSRF, internal port-scan).
- Forge preference cookies and CSRF tokens.

The same risk holds for the other placeholders this detector catches:
they are documented sentinels, not real keys.

## References

- SearXNG `settings.yml` reference, `server.secret_key`
  <https://docs.searxng.org/admin/settings/settings_server.html>
- searxng/searxng-docker README — "You **must** generate a secret key"
- CWE-798: Use of Hard-coded Credentials

## Usage

```
./detect.sh path/to/settings.yml
cat settings.yml | ./detect.sh -
```

Exit codes:

- `0` — no issue found
- `1` — at least one default/placeholder secret key found
- `2` — usage / IO error
