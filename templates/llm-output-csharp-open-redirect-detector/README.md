# llm-output-csharp-open-redirect-detector

**CWE:** [CWE-601 — URL Redirection to Untrusted Site (Open Redirect)](https://cwe.mitre.org/data/definitions/601.html)
**Language:** C# / ASP.NET (Core + classic MVC + Web API)
**Static analysis only.** Defensive linter for LLM-generated code.

## What it catches

LLMs writing ASP.NET controllers love to bounce the user back to a
caller-supplied URL after login, after logout, after a webhook
callback, after an OAuth flow, etc. The shortest-path emission is:

```csharp
public IActionResult Login(string returnUrl)
{
    return Redirect(returnUrl);
}
```

That sink takes any absolute URL, including `https://evil.example/...`,
and the framework will happily issue the 302. This is the textbook
open-redirect (CWE-601) pattern; it powers phishing, OAuth-code theft,
and referrer-token leakage.

This detector flags lines that:

1. invoke a redirect sink — `Redirect`, `RedirectPermanent`,
   `RedirectPreserveMethod`, `RedirectPermanentPreserveMethod`,
   `RedirectToAction`, `Response.Redirect`, or
   `new RedirectResult(...)`; **and**
2. pass an argument that contains a tainted-source token —
   `Request.`, `Query[`, `Form[`, `Headers[`, `Cookies[`,
   `RouteData`, `returnUrl`, `redirectUrl`, `redirect_uri`,
   `next_url`, bare `next` / `target` / `url` parameters,
   `Model.`, `dto.`, `input.`, `ViewBag.`, `TempData[`.

## What suppresses a finding

The detector treats the *entire file* as opted-in if any of these
tokens appear:

- `LocalRedirect(`, `LocalRedirectPermanent(`,
  `LocalRedirectPreserveMethod(`
- `new LocalRedirectResult(`
- `Url.IsLocalUrl(`

These are the framework-blessed safe sinks: they reject absolute and
scheme-bearing URLs at the framework layer. Per-line silencing is also
available with the trailing comment `// redirect-ok`.

String literals and `//` comments are masked before pattern matching,
so `Redirect("/home")` and `// example: Redirect(returnUrl)` do not
fire.

## Usage

```bash
python3 detect.py path/to/Controllers
python3 detect.py file1.cs file2.cs
```

Exit `1` if any findings, `0` otherwise. Pure stdlib Python 3.

## Worked example

```bash
./verify.sh
# bad findings:  8 (rc=1)
# good findings: 0 (rc=0)
# PASS
```

`examples/bad/` contains three controllers (returnUrl reflection,
query/form/header/cookie reflection, model-bound DTO reflection) for a
total of 8 sinks. `examples/good/` contains literal-only redirects, a
controller that uses `Url.IsLocalUrl` + `LocalRedirect`, and a file
that exercises both the per-line suppression and the
string-literal/comment masking.

## Limits

- Single-file scope. A taint that flows through another file is not
  followed.
- Token-based taint heuristic. A variable named `userTarget` is not
  recognised; rename to `target` or pass through `Request.Query[...]`
  for the detector to fire.
- The mitigation check is file-scoped: any `LocalRedirect`/`IsLocalUrl`
  token in the file silences *all* sinks in that file. Keep mitigated
  and unmitigated controllers in separate files.
- Multi-line redirect calls where the sink name and the tainted token
  sit on different physical lines are not matched.
