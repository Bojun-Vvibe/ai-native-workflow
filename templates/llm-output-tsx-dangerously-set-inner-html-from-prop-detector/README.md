# llm-output-tsx-dangerously-set-inner-html-from-prop-detector

Static detector for the React/TSX anti-pattern of feeding
`dangerouslySetInnerHTML` an `__html` value sourced (transitively) from
component props, route params, request bodies, query strings, or other
caller-controlled inputs — without an obvious sanitizer in the same
expression.

## Why

`dangerouslySetInnerHTML` bypasses React's normal escaping. When the
HTML payload originates from untrusted input, the result is reflected
or stored XSS.

LLM-generated React code very often looks like:

```tsx
<div dangerouslySetInnerHTML={{ __html: props.bio }} />
<div dangerouslySetInnerHTML={{ __html: post.content }} />
<div dangerouslySetInnerHTML={{ __html: req.query.html }} />
```

These all flow attacker-controlled input straight into the DOM as HTML.

## What this flags

Any JSX/TSX `dangerouslySetInnerHTML={{ __html: <expr> }}` where
`<expr>` references one of the following names (case-sensitive root,
allowing dotted/optional-chain/bracket access after it):

* `props`, `props.*`
* a destructured prop name when it appears alongside an obvious
  request-shaped name (`html`, `content`, `body`, `bio`, `description`,
  `markdown`, `raw`, `comment`, `message`, `note`, `text`, `value`,
  `payload`, `data`, `userInput`)
* `req`, `req.*` (Express/Koa/Next handlers)
* `request`, `request.*`
* `router.query`, `useRouter().query`, `searchParams`, `params`
* `window.location.*`
* `location.hash`, `location.search`, `document.URL`, `document.referrer`
* `localStorage.*`, `sessionStorage.*`
* `JSON.parse(<anything containing one of the above sources>)`

A finding is **not** raised when the expression on the right side of
`__html:` is wrapped in an obvious sanitizer call within the same
expression: `DOMPurify.sanitize(...)`, `sanitizeHtml(...)`,
`xss(...)`, `purify(...)`, `escapeHtml(...)`. This is intentionally
shallow — sanitizer wrappers are easy to spot in LLM output, and the
goal is to catch raw assignments, not prove non-XSS.

The detector understands fenced code blocks in markdown (it scans
`.tsx`, `.jsx`, `.ts`, `.js` and also pulls fenced code from `.md`),
strips line/block comments, and ignores text inside string literals.

Per-line suppression marker: `// llm-allow:dangerously-set-inner-html`.

## CWE references

* **CWE-79**: Improper Neutralization of Input During Web Page
  Generation (Cross-site Scripting).
* **CWE-80**: Improper Neutralization of Script-Related HTML Tags.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` if any findings, `0` otherwise. Pure python3 stdlib.

## Worked example

```
$ bash verify.sh
bad findings:  9 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/` and `examples/good/` for the concrete fixtures.
