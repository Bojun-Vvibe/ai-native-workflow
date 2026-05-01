# llm-output-go-html-template-raw-injection-detector

Stdlib-only Python detector that flags **Go** source which bypasses
`html/template`'s contextual auto-escaping by wrapping a runtime
value in one of the *trusted-content* marker types:

| Type                | Context bypassed              |
|---------------------|--------------------------------|
| `template.HTML`     | HTML body / element content    |
| `template.JS`       | `<script>` body                |
| `template.JSStr`    | JS string literal context      |
| `template.CSS`      | `<style>` body                 |
| `template.URL`      | `href=` / `src=` URL attrs     |
| `template.HTMLAttr` | full attribute name+value      |
| `template.Srcset`   | `<img srcset=...>` attribute   |

These conversions tell `html/template` "trust me, this string is
already safe in this context, do not escape it." When the wrapped
value is anything other than a compile-time string literal, an
attacker-controlled value flows straight into the rendered page —
canonical CWE-79 (XSS) in Go templates.

## What's flagged

1. **`go-html-template-bypass-runtime`** — `template.HTML(x)` (or any
   marker type above) where `x` is *not* a static string literal or
   an all-literal `+` chain.
2. **`go-html-template-bypass-format`** — same constructors wrapped
   around `fmt.Sprintf` / `fmt.Sprint` / `fmt.Sprintln`.

Suppress with a trailing `// llm-allow:go-template-raw` on the
relevant line (or anywhere up to the closing newline).

## Why this exact shape

The whole reason Go ships `html/template` instead of `text/template`
for HTML output is that the engine knows the contextual escaping
rules. Wrapping a runtime value in one of the marker types is
essentially `// trust me, bro`. A LLM that "just wants the HTML to
render" reaches for these wrappers because the type system complains
otherwise — and ships XSS to production.

The fix is almost always: pass the raw `string` to `template.Execute`
and let `{{.}}` escape per-context.

## Safe shapes the detector deliberately leaves alone

* `template.Execute(w, userBio)` — no marker type involved.
* `template.HTML("<b>Hello</b>")` — string literal arg.
* `template.HTML("<p>" + "Hello" + "</p>")` — all-literal `+` chain.
* `template.CSS(\`body { background: #fff; }\`)` — backtick raw literal.

## CWE / standards

- **CWE-79**: Improper Neutralization of Input During Web Page
  Generation ('Cross-Site Scripting').
- **OWASP A03:2021** — Injection.
- Background: <https://pkg.go.dev/html/template> (search for "Trusted
  contextually-safe content").

## Limits / known false negatives

- We don't follow let-bindings: `s := userBio + "x"; ... template.HTML(s)`
  is flagged at the `template.HTML(s)` site, but the detector cannot
  prove `s` is tainted — it conservatively flags any non-literal arg.
- Custom packages aliased as `template` (e.g. via dot-import or
  rename) are matched; if you import `html/template` as `tmpl`,
  add `tmpl` to the alias list (see `MARKER_RE` in `detect.py`).
- We do not parse the template body itself; only the call sites that
  manufacture the marker-typed value.

## Usage

```bash
python3 detect.py path/to/file.go
python3 detect.py path/to/dir/   # walks *.go, *.md, *.markdown
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Verify

```
$ bash verify.sh
bad=6/6 good=0/6
PASS
```

### Worked example — `python3 detect.py examples/bad/`

```
$ python3 detect.py examples/bad/
examples/bad/01_template_html_runtime.go:11: go-html-template-bypass-runtime: template.HTML(<runtime value>) bypasses html/template auto-escape (CWE-79): tmpl.Execute(w, template.HTML(userBio))
examples/bad/02_template_js_sprintf.go:11: go-html-template-bypass-format: template.JS(fmt.Sprintf...) bypasses html/template auto-escape (CWE-79): js := template.JS(fmt.Sprintf("greet(%q);", name))
examples/bad/03_template_url_runtime.go:11: go-html-template-bypass-runtime: template.URL(<runtime value>) bypasses html/template auto-escape (CWE-79): t.Execute(w, template.URL(userURL))
examples/bad/04_template_css_concat.go:10: go-html-template-bypass-runtime: template.CSS(<runtime value>) bypasses html/template auto-escape (CWE-79): style := template.CSS("background:" + color)
examples/bad/05_template_htmlattr_concat.go:9: go-html-template-bypass-runtime: template.HTMLAttr(<runtime value>) bypasses html/template auto-escape (CWE-79): attr := template.HTMLAttr(`data-x="` + payload + `"`)
examples/bad/06_template_srcset_runtime.go:10: go-html-template-bypass-runtime: template.Srcset(<runtime value>) bypasses html/template auto-escape (CWE-79): t.Execute(w, template.Srcset(candidates))
$ echo $?
1
```

### Worked example — `python3 detect.py examples/good/`

```
$ python3 detect.py examples/good/
$ echo $?
0
```

Layout:

```
examples/bad/
  01_template_html_runtime.go      # template.HTML(userBio)
  02_template_js_sprintf.go        # template.JS(fmt.Sprintf(...))
  03_template_url_runtime.go       # template.URL(userURL) — javascript: bypass
  04_template_css_concat.go        # template.CSS("background:"+color)
  05_template_htmlattr_concat.go   # template.HTMLAttr(`data-x="`+x+`"`)
  06_template_srcset_runtime.go    # template.Srcset(candidates)
examples/good/
  01_no_marker_string.go           # raw string, let the template escape
  02_template_html_literal.go      # template.HTML("<b>...</b>")
  03_template_html_literal_concat.go # template.HTML("<p>"+"Hi"+"</p>")
  04_template_jsstr_literal.go     # template.JSStr("dark-mode")
  05_template_css_raw_literal.go   # template.CSS(`body { ... }`)
  06_suppressed.go                 # explicit // llm-allow:go-template-raw
```
