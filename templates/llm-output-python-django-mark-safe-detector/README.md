# llm-output-python-django-mark-safe-detector

A pure-stdlib python3 line scanner that flags Python source where a
Django web app marks attacker-influenceable strings as **safe HTML**,
disabling the framework's auto-escaping and re-introducing XSS.

LLMs reach for `mark_safe` because the tutorial they trained on shows
it as the fix for *"the HTML is being escaped in my page"* — without
explaining that the entire point of escaping is to prevent the
browser from executing markup pasted in by users.

## What this flags

In `*.py` files, a call site is flagged when the **first argument is
not a bare string literal** (no f-prefix, no concatenation, no
`%` / `format()` / variable / function call):

* `mark_safe(<expr>)` — `django.utils.safestring.mark_safe`
* `SafeString(<expr>)` — `django.utils.safestring.SafeString`
* `SafeText(<expr>)` — legacy alias

In `*.html` / `*.htm` / `*.djhtml` template files, the line is
flagged when the `|safe` filter is applied to a template variable:

* `{{ user_bio|safe }}`
* `{{ form.cleaned_data.bio|safe }}`

A "bare string literal" is one of:

* `'literal'` — single-quoted, no interpolation
* `"literal"` — double-quoted, no interpolation
* `'''literal'''` / `"""literal"""` — triple-quoted, on one line

Anything else is treated as non-literal and is flagged.

## What this does NOT flag

* `mark_safe("<b>fixed</b>")` — fully literal, developer-controlled.
* `format_html("<div>{}</div>", value)` — auto-escapes `{}` placeholders.
* `escape(value)` — explicit escape.
* Lines suffixed with the suppression marker `# mark-safe-ok`.
* Mentions inside docstrings or comments.

## CWE references

* **CWE-79**  Improper Neutralization of Input During Web Page Generation (XSS).
* **CWE-80**  Improper Neutralization of Script-Related HTML Tags.
* **CWE-116** Improper Encoding or Escaping of Output.

## Usage

```
python3 detector.py <file_or_dir> [...]
```

Scans `*.py`, `*.html`, `*.htm`, `*.djhtml` under any directory
passed in. Exit `1` if any findings, `0` otherwise. python3 stdlib
only — no Django install required.

## Verified worked example

```
$ bash test.sh
bad findings: 6 (expected 6)
good findings: 0 (expected 0)
PASS
```

Real run output over the fixtures:

```
$ python3 detector.py fixtures/bad/
fixtures/bad/01_mark_safe_request_post.py:6: mark_safe() called with non-literal argument: return mark_safe(bio)
fixtures/bad/03_safestring_fstring.py:4: SafeString() called with non-literal argument: return SafeString(f"<p>{comment}</p>")
fixtures/bad/04_mark_safe_variable.py:5: mark_safe() called with non-literal argument: return mark_safe(html)
fixtures/bad/02_mark_safe_concat.py:4: mark_safe() called with non-literal argument: return mark_safe("<b>" + name + "</b>")
fixtures/bad/05_template_safe_filter.html:4: |safe filter applied to template variable 'user_bio': <div class="bio">{{ user_bio|safe }}</div>
fixtures/bad/05_template_safe_filter.html:5: |safe filter applied to template variable 'profile.signature_html': <div class="sig">{{ profile.signature_html|safe }}</div>

$ python3 detector.py fixtures/good/
(no output, exit 0)
```

## Limitations

* Single-line scanner. A `mark_safe(\n    expr\n)` is examined
  line-by-line; if the first argument is on a different line than
  the call name the detector may miss it.
* The detector does not understand Django's `format_html_join` or
  custom subclasses of `SafeString`.
* Template scanning is regex-based; deeply nested `{% %}` blocks
  with embedded expressions are not parsed.
* The "bare literal" check rejects f-strings even when they have no
  `{}` placeholders, on the principle that f-prefix is a flag for
  "intends to interpolate eventually".

## Suppression

Append `# mark-safe-ok` to the offending line after a code review:

```python
return mark_safe(f"<i>{name}</i>")  # mark-safe-ok
```
