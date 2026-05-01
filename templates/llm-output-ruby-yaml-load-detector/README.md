# llm-output-ruby-yaml-load-detector

Stdlib-only Python detector that flags **Ruby** source where YAML is
parsed with the unsafe entry points: `YAML.load`, `YAML.load_file`,
`YAML.load_stream`, `YAML.unsafe_load`, `YAML.unsafe_load_file`, or
the equivalent `Psych.*` spellings. These methods reconstruct
arbitrary Ruby objects from the input stream — the canonical
deserialization-RCE shape behind CVE-2013-0156 and the long tail of
copy-cat findings since.

LLMs reach for `YAML.load` because it's the first method shown in the
Ruby docs and because the safer cousin (`YAML.safe_load`, or in
Psych >= 4 `YAML.load(..., permitted_classes: [...])`) requires the
caller to think about the schema.

## Why this exact shape

`YAML.load(io)` on Psych < 4 is fully unsafe — any tag in the document
can instantiate any class. `Psych.unsafe_load` is the explicit
"give me the old behavior" knob. We treat both as findings, plus
`load_file` / `load_stream` since they thread the same code path.

The **safe** spellings the detector deliberately leaves alone:

- `YAML.safe_load`, `YAML.safe_load_file`, `YAML.safe_load_stream`
- `Psych.safe_load`
- `YAML.load(..., permitted_classes: [...])` — the modern Psych >= 4
  form. We treat the presence of a `permitted_classes:` kwarg within
  3 lines of the call as opt-in to safe semantics.

## Heuristic

A finding is emitted when:

1. The line (after stripping `# ...` comments) matches
   `\b(?:YAML|Psych)\.(?:load|load_file|load_stream|unsafe_load|unsafe_load_file)\(`.
2. There is **no** `permitted_classes:` kwarg on that line or the
   next two lines.

That window is intentionally tight — wide enough to catch the typical
multi-line `YAML.load(body, permitted_classes: [...])` call, narrow
enough that an unrelated `permitted_classes:` later in the file
won't suppress a real finding.

## CWE / standards

- **CWE-502**: Deserialization of Untrusted Data.
- **OWASP A08:2021** — Software and Data Integrity Failures.
- Historical reference: CVE-2013-0156 (Rails YAML deserialization),
  CVE-2017-0903 (RubyGems YAML).

## Limits / known false negatives

- We don't follow aliases like `Y = YAML; Y.load(...)`.
- We don't analyze whether the *input* is actually attacker-reachable;
  every `YAML.load` is treated as a finding by default. For trusted
  hand-authored YAML on the local disk this is technically a false
  positive — fix it by switching to `safe_load` anyway, which costs
  nothing.
- Heredocs and multi-line string args that span more than 3 lines
  before the `permitted_classes:` kwarg will be flagged. Reformat the
  call onto fewer lines or use `safe_load`.

## Usage

```bash
python3 detect.py path/to/file.rb
python3 detect.py path/to/dir/   # walks *.rb, *.rb.txt, *.erb, *.rake, *.gemspec
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

### Worked example — `bash detect.py examples/bad/`

```
$ python3 detect.py examples/bad/
examples/bad/03_psych_load.rb:7: YAML.load / Psych.load on possibly untrusted input (CWE-502): Psych.load(raw)   # cache value comes back as full Ruby objects
examples/bad/04_load_stream_loop.rb:5: YAML.load / Psych.load on possibly untrusted input (CWE-502): YAML.load_stream(body) do |doc|
examples/bad/06_psych_load_file.rb:5: YAML.load / Psych.load on possibly untrusted input (CWE-502): config = Psych.load_file(config_path)
examples/bad/02_load_file_uploaded.rb:6: YAML.load / Psych.load on possibly untrusted input (CWE-502): payload = YAML.load_file(upload_path)
examples/bad/05_unsafe_load_explicit.rb:7: YAML.load / Psych.load on possibly untrusted input (CWE-502): YAML.unsafe_load(io.read)
examples/bad/01_load_request_body.rb:6: YAML.load / Psych.load on possibly untrusted input (CWE-502): config = YAML.load(request.body.read)
$ echo $?
1
```

### Worked example — `bash detect.py examples/good/`

```
$ python3 detect.py examples/good/
$ echo $?
0
```

Layout:

```
examples/bad/
  01_load_request_body.rb     # YAML.load on request body
  02_load_file_uploaded.rb    # YAML.load_file on user-uploaded path
  03_psych_load.rb            # Psych.load on Redis cache value
  04_load_stream_loop.rb      # YAML.load_stream on webhook body
  05_unsafe_load_explicit.rb  # YAML.unsafe_load (the explicit knob)
  06_psych_load_file.rb       # Psych.load_file on CLI argv
examples/good/
  01_safe_load.rb             # YAML.safe_load
  02_safe_load_file.rb        # YAML.safe_load_file
  03_psych_safe_load.rb       # Psych.safe_load
  04_load_with_permitted_classes.rb  # Psych >= 4 permitted_classes opt-in
  05_json_instead.rb          # JSON.parse — wrong format, no gadget
  06_safe_load_stream.rb      # YAML.safe_load_stream + permitted_classes
```
