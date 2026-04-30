# llm-output-python-hardcoded-password-detector

A pure-stdlib python3 line scanner that flags hard-coded credentials in
LLM-emitted Python source. LLMs love to autocomplete a placeholder like
``password = "changeme"`` because the demo "just works" — but the
literal is then committed, indexed by GitHub code search, scraped, and
re-used by the next attacker.

## What this flags

A line is flagged when it contains an assignment to a name that looks
like a credential and the right-hand side is a non-empty string literal.

Credential-looking names (case-insensitive, word-boundary):

* ``password``, ``passwd``, ``pwd``
* ``secret``, ``api_key``, ``apikey``, ``api_token``
* ``access_token``, ``auth_token``, ``bearer_token``, ``refresh_token``
* ``private_key``, ``client_secret``, ``aws_secret_access_key``
* ``db_password``, ``database_password``, ``postgres_password``,
  ``mysql_password``, ``redis_password``

Detected forms:

* Module-level / class-attribute assignment:
  ``PASSWORD = "hunter2"``
* dict-literal entry:
  ``cfg = {"password": "hunter2"}``
* keyword argument in a call:
  ``connect(password="hunter2")``

## What this does NOT flag

* Empty literal: ``password = ""`` (intentional placeholder).
* Reading from env / vault: ``password = os.getenv("DB_PASS")``,
  ``password = secrets.token_urlsafe(32)``, ``password = config["db"]``.
* Type annotation only: ``password: str`` (no value).
* Test-only sentinels recognised by the suppression marker
  ``# hardcoded-password-ok`` at end of line.
* Names that merely *contain* "key" but aren't credential-like —
  e.g. ``primary_key``, ``foreign_key``, ``sort_key``, ``cache_key``,
  ``partition_key``, ``public_key`` (public material, not secret).

## CWE references

* **CWE-798** Use of Hard-coded Credentials
* **CWE-259** Use of Hard-coded Password
* **CWE-321** Use of Hard-coded Cryptographic Key

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit status `1` if any findings, `0` otherwise. python3 stdlib only,
no third-party deps.

## Limitations

* Single-line scanner. Multi-line assignments
  (`password = (\n    "hunter2"\n)`) are not joined; only the line with
  the literal is examined and may miss the LHS.
* No taint analysis: a string literal that *happens* to be later
  XOR'd, sliced, base64-decoded etc. is still flagged.
* The allow-list of "looks-like-public-material" names is intentionally
  small; widen it in your project fork if needed.
