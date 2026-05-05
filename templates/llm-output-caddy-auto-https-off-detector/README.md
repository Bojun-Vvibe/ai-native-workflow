# llm-output-caddy-auto-https-off-detector

Detects Caddy web-server configurations that disable Caddy's
automatic HTTPS / certificate-management feature, leaving the
listener serving plaintext HTTP on its public port.

Surfaces covered:

* `Caddyfile` global option `auto_https off` (and the
  `auto_https disable_redirects` weaker form when combined with the
  full off switch elsewhere)
* `caddy.json` adapter output: `apps.http.servers.<name>.automatic_https.disable: true`
* `docker-compose.yml` env / command flags overriding the Caddyfile
  with `--auto-https off` style invocations
* Dockerfile / shell `CMD ["caddy","run","--auto-https","off"]`

## Why this matters

Caddy's headline feature is automatic, on-by-default ACME issuance
and HTTP→HTTPS redirection. Operators occasionally set
`auto_https off` while diagnosing local DNS issues and forget to
revert it; LLM-generated quickstarts copy that snippet because it is
what shows up in the top StackOverflow answer for "Caddy ACME
failing during local dev".

When the toggle is left off in production:

* The listener serves the application over plaintext HTTP on `:80`
  with no upgrade path.
* Browsers that previously cached an HSTS pin will fail closed; new
  visitors will silently submit credentials in cleartext.
* Caddy stops renewing existing certificates, so the cutover from a
  previously-HTTPS site to a silently-plaintext one is invisible
  until the cached cert expires.

This is a different mechanism from "TLS misconfigured" (weak
ciphers / old protocols) — here, TLS is not being attempted at all.

## Rules

A finding is emitted when a recognised Caddy config surface
explicitly turns the feature off:

* Caddyfile global block: `auto_https off`
* JSON config: `"automatic_https": { "disable": true }` (truthy
  variants accepted)
* Command line / env: a `caddy run` invocation that includes
  `--auto-https off` or sets `CADDY_AUTO_HTTPS=off`

Suppression: the magic comment `# caddy-auto-https-off-allowed`
silences the finding (intended for ephemeral local-dev compose files
that only listen on `127.0.0.1`).

## Run

```
python3 detector.py examples/bad/01_caddyfile_global_off.Caddyfile
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Out of scope

* `tls internal` (Caddy's local CA) — that is a *different* posture:
  TLS is still on, just with a non-public CA. Local-dev convenience,
  not a plaintext-on-the-wire issue.
* HSTS header absence — separate header-policy detector niche.
* Reverse-proxy `transport http` blocks pointing at plaintext
  upstreams — that is upstream posture, not listener posture.

## References

* Caddy docs, "Automatic HTTPS" page — describes the off switch
  and warns that disabling it bypasses certificate management
  entirely.
* Caddy global options reference — `auto_https` documented values.
