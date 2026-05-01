# llm-output-rails-mass-assignment-permit-all-detector

Static lint that flags Rails strong-parameter handlers which accept arbitrary
attributes, defeating the mass-assignment guard that strong_params is
supposed to provide.

LLM-generated Rails controllers frequently shortcut the strong_params dance
by writing one of the patterns below. Any of them allow an attacker to set
sensitive attributes (`admin`, `role`, `stripe_customer_id`,
`confirmed_at`, ...) by adding them to the request body — the canonical
mass-assignment vulnerability that strong_params was introduced to prevent.

## What it catches

- `params.permit!` (and chained variants like `params.require(:user).permit!`)
- `params[:foo].permit!`
- `params.permit(params.keys)` / `params.permit(*params.keys)`
- `params.require(:foo).permit(params[:foo].keys)`
- `Model.new(params[:foo])`, `Model.create(params[:foo])`,
  `Model.update(params[:foo])`, `Model.assign_attributes(params[:foo])` —
  any persistence call that takes a raw `params[:x]` hash without going
  through `.permit`
- The same persistence calls on instance receivers
  (`@user.update(params[:user])`, `current_user.account.update(params[...])`)

## CWE references

- [CWE-915](https://cwe.mitre.org/data/definitions/915.html): Improperly
  Controlled Modification of Dynamically-Determined Object Attributes
- [CWE-284](https://cwe.mitre.org/data/definitions/284.html): Improper
  Access Control

## False-positive surface

- **Internal admin actions** where every attribute really should be
  writable. Suppress per line with a trailing `# mass-assignment-allowed`
  annotation.
- **Test factories / seed scripts** that use `Model.create(attrs)` with a
  locally-built hash. Mitigate by excluding `spec/`, `test/`, `db/seeds*`,
  `db/fixtures/` at the invocation layer.
- **DSL-style code** where `params` is a local variable, not the Rails
  request hash. The detector keys on the literal token `params` and cannot
  distinguish; suppress per line if needed.

## Usage

```
python3 detector.py path/to/file_or_dir [more paths ...]
```

Exit code is the number of files with at least one finding (capped at 255).
Stdout lists `<file>:<line>:<reason>` for every match. Only `*.rb` files are
scanned when a directory is passed.

## Verification

`verify.sh` runs the detector against `examples/bad/` and `examples/good/`
and asserts every bad sample fires and zero good samples fire. Latest run:

```
bad=6/6 good=0/4
PASS
```
