# `llm-output-url-scheme-allowlist-validator`

Pure stdlib detector that scans an LLM-emitted text blob for URLs and
flags any URL whose **scheme** is not in a caller-supplied allow-list.
Five finding kinds:

- `disallowed_scheme` — scheme present but not allow-listed
  (`javascript:`, `file:`, `data:`, `vbscript:`, …)
- `scheme_relative` — `//host/path` with no scheme (defers to the
  renderer's current scheme — unsafe to ship from an LLM)
- `bare_host_https_likely` — text shaped like `example.com/path` with
  no scheme (caller decides whether to auto-prefix `https://` or reject)
- `unicode_scheme` — the scheme contains non-ASCII characters that may
  visually mimic an allow-listed scheme (e.g. Cyrillic `р` inside
  `httрs:`)
- (no finding) — every URL is allow-listed

Default allow-list is `frozenset({"https", "http", "mailto"})`.

## When to use

- Pre-publish gate on any LLM-generated **markdown / HTML / blog
  post / status update / chat message** that will be rendered to a
  browser, an editor preview, or a Slack message — `javascript:`,
  `data:text/html`, and unicode-scheme URLs are the three most
  common XSS-via-LLM smuggle paths.
- Pre-commit guardrail on AI-generated **documentation PRs** so a
  silently-injected `data:` URI doesn't make it into a published doc.
- Audit step in a **review-loop** (compose with
  [`agent-output-validation`](../agent-output-validation/) and
  [`llm-output-trust-tiers`](../llm-output-trust-tiers/)) — a finding
  forces the output one tier toward `human_review`.

## Inputs / outputs

```
validate_urls(text: str, allow: frozenset[str] = DEFAULT_ALLOW) -> list[Finding]

Finding(kind: str, offset: int, url: str, scheme: Optional[str])
```

- `text` — the LLM output to scan. Must be `str` (raises
  `ValidationError` otherwise).
- `allow` — `frozenset` of lower-cased scheme names. Entries that are
  not lower-cased non-empty `str` raise `ValidationError`. Default
  `{"https", "http", "mailto"}`.
- Returns the list of findings sorted by `(offset, kind, url)` so two
  runs over the same input produce **byte-identical** output (cron- /
  CI-friendly diffing).
- `format_report(findings)` renders a deterministic plain-text report.

The detector is a **pure function** over a string: no I/O, no clocks,
no DNS, no HTTP. It does not validate that an `https://` URL exists —
only that its **shape** is allow-listed.

## Composition

- [`llm-output-trust-tiers`](../llm-output-trust-tiers/) — any finding
  forces a demotion (`auto_apply` → `shadow_apply` or lower).
- [`prompt-pii-redactor`](../prompt-pii-redactor/) — orthogonal: this
  template guards rendering surface, the redactor guards content
  surface. Run both.
- [`agent-trace-redaction-rules`](../agent-trace-redaction-rules/) —
  scrub findings from persisted forensic traces.
- [`structured-error-taxonomy`](../structured-error-taxonomy/) — a
  finding classifies as `do_not_retry` / `attribution=model`: the
  model itself wrote the bad URL, so retrying without prompt change is
  pointless.

## Worked example

```
$ python3 example.py
```

Verbatim output:

```
allow-list: ['http', 'https', 'mailto']

=== 01-clean ===
input: 'See https://example.com/docs and email us at mailto:hi@example.com for details.'
OK: no disallowed URL schemes found.

=== 02-javascript-smuggle ===
input: 'Click [here](javascript:alert(1)) to confirm. Also see https://example.com.'
FOUND 1 URL finding(s):
  [disallowed_scheme] offset=13 scheme=javascript url=javascript:alert(1

=== 03-scheme-relative-and-bare ===
input: 'Load //cdn.example.com/x.js then visit example.com/landing for more.'
FOUND 2 URL finding(s):
  [scheme_relative] offset=5 scheme=- url=//cdn.example.com/x.js
  [bare_host_https_likely] offset=39 scheme=- url=example.com/landing

=== 04-data-uri ===
input: 'The summary is at data:text/html;base64,PHA+aGk8L3A+ which inlines.'
FOUND 1 URL finding(s):
  [disallowed_scheme] offset=18 scheme=data url=data:text/html;base64,PHA+aGk8L3A+

=== 05-unicode-scheme-attack ===
input: 'Open httpsр://login.example.com to verify (р is Cyrillic).'
FOUND 1 URL finding(s):
  [unicode_scheme] offset=5 scheme=httpsр url=httpsр://login.example.com

```

Notes:

- Case 02 truncates the captured URL at `(` because `)` is in the
  URL-terminating boundary set — that's the correct shape for URLs
  embedded inside markdown `[text](url)` parens. The `disallowed_scheme`
  classification fires on the scheme `javascript`, which is what matters
  for the gate.
- Case 03 reports both kinds at distinct offsets — the scheme-relative
  URL and the bare host are independent findings, not one shadowing
  the other.
- Case 04 catches `data:text/html;base64,…` — the most common XSS-via-LLM
  vehicle in published markdown.
- Case 05 surfaces the Cyrillic `р` (U+0440) inside `https`. The folded
  ASCII would *match* the allow-list, but the surface form would render
  as a non-resolvable host — caller should treat `unicode_scheme` as
  always-suspect.

## Files

- `validator.py` — pure stdlib detector + `format_report`
- `example.py` — five-case worked example
