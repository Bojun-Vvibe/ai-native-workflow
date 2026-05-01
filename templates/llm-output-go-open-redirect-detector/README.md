# llm-output-go-open-redirect-detector

Stdlib-only Python detector that flags **Go HTTP handlers** which feed
user-controlled input straight into `http.Redirect` or a manually-set
`Location` header without any allow-list / validation. This is the
canonical CWE-601 (URL Redirection to Untrusted Site, "Open Redirect")
shape.

LLMs love to emit this exact pattern when a user asks for a
post-login `?next=` redirect: the model reads `r.URL.Query().Get("next")`
and hands it directly to `http.Redirect`, which happily issues a 302 to
`attacker.example.com`.

## Why it matters

An attacker who can control the redirect destination can:

- Phish credentials by bouncing victims through your trusted domain
  before landing on a lookalike login page.
- Bypass referer-based CSRF checks on third-party sites that trust
  your origin.
- Turn an OAuth `state` mismatch into a working account-takeover
  primitive when paired with a stolen `code`.

The fix is always the same shape: validate the destination against an
allow-list, or restrict it to relative paths (`strings.HasPrefix(dest, "/")`
plus a check that it doesn't start with `//`).

## Heuristic

A finding is emitted when, **inside the same Go function body**:

1. User input is read from one of:
   - `r.URL.Query().Get(...)`
   - `r.FormValue(...)`
   - `r.PostFormValue(...)`
   - `r.URL.Query()[...]`
   - `mux.Vars(r)[...]`
   ... captured into an identifier (or used inline).

2. The same identifier (or a `+`-concat / `fmt.Sprintf` containing it,
   or one of the inline source expressions above) is passed as the
   destination argument of:
   - `http.Redirect(w, r, <dest>, code)`
   - `w.Header().Set("Location", <dest>)`
   - `w.Header().Add("Location", <dest>)`

3. The function body does **not** contain any of these allow-list /
   validation hints (which would suppress the finding):
   - `allowed*[...]` map lookup
   - `validate*Redirect(`, `isSafeRedirect(`, `safeRedirect(`
   - `url.Parse(` followed by a `.Hostname() ==` comparison
   - `strings.HasPrefix(<expr>, "/")`

The function splitter is a small hand-rolled brace-balancer that
respects Go string literals (`"..."` and ``` `...` ```) and `//` line
comments.

## CWE / standards

- **CWE-601**: URL Redirection to Untrusted Site ("Open Redirect").
- **CWE-20**: Improper Input Validation (parent).
- **OWASP A01:2021** — Broken Access Control (open redirects are
  routinely chained with auth bypass).

## Limits / known false negatives

- We don't follow variable assignments across function boundaries. If
  the destination is sanitized in a helper that doesn't match one of
  our allow-list hints, we'll emit a finding and you'll have to add a
  comment or rename the helper to match (e.g. `safeRedirect`).
- We don't detect taint that flows through a struct field
  (`req.Next = r.FormValue(...)`; `http.Redirect(w, r, req.Next, ...)`).
- We treat `strings.HasPrefix(x, "/")` as sufficient validation, which
  is technically too permissive: an attacker can supply `//evil.com`
  and most browsers will treat it as `https://evil.com`. We assume the
  reviewer who saw `HasPrefix` already knows about that nuance.

These are deliberate trade-offs to keep false positives near zero on
real-world handler code.

## Usage

```bash
python3 detect.py path/to/file.go
python3 detect.py path/to/dir/   # walks *.go and *.go.txt
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_query_next.go         # ?next= → http.Redirect
  02_form_value.go         # FormValue → http.Redirect
  03_location_header.go    # PostFormValue → Location header
  04_mux_vars.go           # mux.Vars → http.Redirect
  05_sprintf_host.go       # fmt.Sprintf with tainted host
  06_inline_formvalue.go   # inline FormValue as redirect dest
examples/good/
  01_literal.go                  # literal destination only
  02_allowlist_lookup.go         # map[string]string allow-list
  03_relative_only.go            # HasPrefix "/" guard
  04_url_parse_host_check.go     # url.Parse + Hostname() check
  05_validator_helper.go         # validateRedirect() helper
  06_constant_location.go        # constant Location header
```
