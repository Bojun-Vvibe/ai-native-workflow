# llm-output-graphql-introspection-enabled-prod-detector

Static lint that flags GraphQL server bootstraps where introspection is left
enabled in production-shaped contexts. LLM-generated GraphQL code frequently
copies the development defaults from quickstart docs (Apollo Server,
graphql-yoga, Strawberry, Ariadne, graphene-django) and ships to production
with the schema fully introspectable. Public introspection lets an attacker
enumerate every type, field, and argument in the API surface, which
trivializes recon for authorization-bypass and injection attacks.

## What it catches

- `introspection: true` in JS/TS Apollo / yoga config blocks
- JSON / YAML configs with `"introspection": true`
- Python kwargs `introspect=True` / `introspection=True` (Ariadne, Graphene)
- `'INTROSPECTION': True` in Django `GRAPHENE` settings dict
- `NoSchemaIntrospectionCustomRule` referenced *only* inside a comment
  (i.e. someone commented out the validation rule before deploy)

A finding fires only when the file *also* shows a production signal in a
±80-line window:

- `NODE_ENV === "production"`
- `ENV == 'prod'` / `ENV = 'production'`
- `settings.production`
- `DEBUG = False`
- `app.config['ENV'] = 'production'`
- `FLASK_ENV = 'production'`
- a Dockerfile-style `CMD` line
- `DJANGO_SETTINGS_MODULE` referencing `prod`
- or the filename contains `prod`, `production`, or `deploy`

This keeps dev/test files from being flagged.

## CWE references

- [CWE-200](https://cwe.mitre.org/data/definitions/200.html): Exposure of
  Sensitive Information to an Unauthorized Actor
- [CWE-540](https://cwe.mitre.org/data/definitions/540.html): Inclusion of
  Sensitive Information in Source Code
- [CWE-668](https://cwe.mitre.org/data/definitions/668.html): Exposure of
  Resource to Wrong Sphere

## False-positive surface

- **Test fixtures** that intentionally enable introspection. Mitigate by
  excluding `**/tests/**` and `**/__tests__/**` at the invocation layer.
- **Internal admin consoles** where introspection is desired. Suppress per
  line with a trailing `# graphql-introspection-allowed` (or `//
  graphql-introspection-allowed`) annotation.
- **Library re-exports** of `NoSchemaIntrospectionCustomRule`. The
  commented-rule heuristic only fires when *no* uncommented usage of the
  symbol appears as a value (imports/`require` calls are ignored).

## Usage

```
python3 detector.py path/to/file_or_dir [more paths ...]
```

Exit code is the number of files with at least one finding (capped at 255).
Stdout lists `<file>:<line>:<reason>` for every match.

## Verification

`verify.sh` runs the detector against `examples/bad/` and `examples/good/`
and asserts every bad sample fires and zero good samples fire. Latest run:

```
bad=6/6 good=0/5
PASS
```
