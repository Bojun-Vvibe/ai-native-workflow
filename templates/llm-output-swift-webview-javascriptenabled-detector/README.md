# llm-output-swift-webview-javascriptenabled-detector

Stdlib-only Python detector that flags **Swift / Objective-C** WebView
configurations and JS-injection sinks LLMs habitually emit when asked
to "embed a help page", "render the article HTML", or "inject a tiny
script to set the title". This is the canonical iOS CWE-79
(Cross-Site Scripting) vehicle: an in-app WebView with JavaScript
enabled, fed an attacker-influenced page or an attacker-influenced
script string.

## What it flags

| Pattern | Kind | Why it's bad |
|---|---|---|
| `UIWebView` (any reference) | `swift-uiwebview` | Apple-deprecated; JS is on by default; no isolation. |
| `preferences.javaScriptEnabled = true` | `swift-webview-jsenabled` | Enables JS on a `WKWebView`. |
| `WKWebpagePreferences.allowsContentJavaScript = true` | `swift-webview-jsenabled` | Modern API path to the same risk. |
| `webView.evaluateJavaScript(<non-literal>)` | `swift-webview-evaljs-nonliteral` | String-built JS injected into the page (XSS via the host app). |
| `webView.loadHTMLString(<non-literal>, baseURL: ...)` | `swift-webview-loadhtml-nonliteral` | Renders attacker-influenced HTML in the app's WebView origin. |

A pure string-literal argument to `evaluateJavaScript` /
`loadHTMLString` is exempted — it cannot embed untrusted data.

## Why it matters

When the WebView origin is the app itself (or `file://` / `about:blank`)
and JavaScript is enabled, any injected script can:

* Read app-local files via `file://` references.
* Call back into the native bridge (`WKScriptMessageHandler`) and
  invoke privileged native code.
* Steal session cookies / tokens that the WebView has access to.

Common LLM-emitted shapes the detector catches:

```swift
let cfg = WKWebViewConfiguration()
cfg.preferences.javaScriptEnabled = true
let web = WKWebView(frame: .zero, configuration: cfg)

web.evaluateJavaScript("document.title = '\(name)';")  // tainted interpolation
web.loadHTMLString(serverHtml, baseURL: nil)           // tainted body
```

The fix:

* Leave `javaScriptEnabled = false` (the default for new WebViews
  created without a custom configuration is already to disable JS in
  many product configurations — be explicit about it).
* Pass static literal HTML / JS strings only.
* For dynamic content, render server-side to a sanitized HTML and
  serve it from a known, locked-down origin; never `loadHTMLString`
  from raw network bytes.
* Stop using `UIWebView` entirely — it is deprecated by Apple.

## Heuristic details

1. Comments (`//`, `/* */`) and string literals (`"..."`, `@"..."`,
   triple-quoted `"""..."""`) are token-blanked before scanning so
   risky tokens that appear only in strings or comments do not match.
2. Markdown files are scanned by extracting fenced
   `` ```swift ``/`objc`/`objective-c` blocks; line numbers are
   preserved. Prose mentions are ignored.
3. Per-line suppression marker (in any `//` comment on that line):
   `// llm-allow:swift-webview-js`.

## Running

```bash
python3 detect.py path/to/Sources
python3 detect.py App.swift Bridge.m README.md
```

Exits `1` if any findings are emitted, `0` otherwise. Findings are
printed as `path:lineno: <kind>(<detail>)`.

## Worked example

```bash
./verify.sh
```

Confirms the detector trips on every file in `examples/bad/`
(≥6 findings across 6 samples) and stays silent on every file in
`examples/good/`. Script exits `0` and prints `PASS` on success.

## Files

* `detect.py` — the matcher (Python 3 stdlib only).
* `verify.sh` — runs detector on `examples/bad/` and `examples/good/`,
  asserts `bad>=6, good=0`, prints `PASS` / `FAIL`.
* `examples/bad/` — six samples that MUST trip (jsEnabled=true,
  allowsContentJavaScript=true, UIWebView, evaluateJavaScript on a
  built string, loadHTMLString on a variable, fenced markdown block).
* `examples/good/` — six samples that MUST NOT trip (jsEnabled=false,
  literal-only `evaluateJavaScript`, literal-only `loadHTMLString`,
  risky tokens only inside strings/comments, suppression marker,
  markdown prose without fences).
