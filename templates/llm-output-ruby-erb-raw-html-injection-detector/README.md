# llm-output-ruby-erb-raw-html-injection-detector

Static detector for Ruby ERB / Rails view templates where LLM-generated
code emits user-controllable data into HTML *without* the default
escape, reintroducing reflected or stored XSS.

## What it flags

The default Rails ERB output tag `<%= %>` runs every value through
`ERB::Util.html_escape`. The following constructs disable that:

| Construct                    | Why it's risky                                |
| ---------------------------- | --------------------------------------------- |
| `<%= raw(value) %>`          | `raw` returns a `SafeBuffer` -- no escaping.  |
| `<%= value.html_safe %>`     | Marks any string as already-escaped.          |
| `<%== value %>`              | Rails ERB explicit-unescape tag.              |

When `value` is anything user-influenceable (params, cookies, request,
session, instance variables, interpolated strings, concatenations,
`format`/`sprintf` outputs, `current_user.*`, `flash[...]`), the result
is XSS.

## What it does NOT flag

* `<%= raw("<br>") %>` -- argument is a literal.
* `<%= t(".title").html_safe %>` -- I18n translations.
* `<%= sanitize(post.body) %>` -- `sanitize` is an allowlist filter,
  not an unescape.
* Anything outside `*.erb`, `*.rhtml`, `*.html.erb`, `*.erb.txt`.

## Usage

```bash
python3 detect.py path/to/views/
python3 detect.py app/views/posts/show.html.erb
```

Exit codes:

* `0` -- no findings
* `1` -- at least one finding (printed as `path:line: label: snippet`)
* `2` -- usage error

## Verify

```bash
./verify.sh
```

The verify harness asserts every file under `examples/bad/` triggers
the detector and every file under `examples/good/` does not.

## Design notes

The detector is regex-based and stdlib-only on purpose: it is meant to
run as a tight pre-merge gate against LLM-emitted ERB diffs, not as a
full Ruby parser. False positives are tuned down by requiring a
"dynamic input" hint on the unescape sink; false negatives are
acceptable for trivially-literal `raw(...)` calls.
