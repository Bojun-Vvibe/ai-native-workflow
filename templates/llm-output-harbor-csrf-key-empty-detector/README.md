# llm-output-harbor-csrf-key-empty-detector

Detects Harbor (`harbor.yml`) configurations that ship with an empty,
placeholder, environment-unresolved, or low-entropy `csrf_key`.

## Why this matters

Harbor's core API uses `csrf_key` to derive the per-session CSRF token
that protects state-changing endpoints (creating users, granting
admin, configuring replication, registering robot accounts). When the
key is empty / a placeholder like `changeme` / shorter than 32 chars,
the token becomes guessable or constant across deployments, and a
logged-in admin who visits an attacker page can be coerced into
issuing privileged actions cross-site.

LLM-generated `harbor.yml` quickstarts routinely emit:

    csrf_key:

or paste the literal sample value `${HARBOR_CSRF_KEY}` from the
upstream template without resolving the env var. This detector flags
those shapes before the file lands on disk.

## What it detects

For each file, the detector checks the **top-level** `csrf_key:` entry
and reports a finding if the value is any of:

1. Empty (`csrf_key:` with nothing after the colon).
2. A common placeholder (`changeme`, `change-me`, `placeholder`,
   `secret`, `harbor`, `0123456789abcdef`, ...).
3. An unresolved env-var placeholder (`${...}`).
4. Shorter than 32 characters.
5. Contains <= 2 unique characters (e.g. `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`).

If the file looks like a `harbor.yml` (contains `harbor_admin_password`
or both `hostname:` and `http:` blocks at top level) but has **no**
`csrf_key` set at all, that is also reported.

## CWE references

- CWE-352: Cross-Site Request Forgery
- CWE-330: Use of Insufficiently Random Values
- CWE-1188: Insecure Default Initialization of Resource

## False-positive surface

- Local dev fixtures intentionally weak: suppress per file with a top
  comment `# harbor-csrf-key-allowed`.
- The detector only inspects top-level keys (column 0), so an embedded
  `csrf_key:` under a sub-mapping in some unrelated YAML is ignored.

## Usage

    python3 detector.py path/to/harbor.yml

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

## Worked example

Live run against the bundled fixtures:

    $ bash verify.sh
    bad=4/4 good=0/3
    PASS

Per-fixture output:

    $ python3 detector.py examples/bad/empty.harbor.yml
    examples/bad/empty.harbor.yml:5:csrf_key is empty
    $ python3 detector.py examples/bad/placeholder.harbor.yml
    examples/bad/placeholder.harbor.yml:5:csrf_key is a placeholder value ('changeme')
    $ python3 detector.py examples/bad/short.harbor.yml
    examples/bad/short.harbor.yml:5:csrf_key is only 11 chars; Harbor requires >=32 for adequate entropy
    $ python3 detector.py examples/bad/unresolved-env.harbor.yml
    examples/bad/unresolved-env.harbor.yml:5:csrf_key is an unresolved env placeholder ('${HARBOR_CSRF_KEY}')

Good fixtures all return exit code 0 and emit no lines.
