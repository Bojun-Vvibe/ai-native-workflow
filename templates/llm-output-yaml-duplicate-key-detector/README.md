# llm-output-yaml-duplicate-key-detector

A pure-stdlib, code-fence-aware detector for **duplicate mapping keys**
inside YAML code blocks emitted by an LLM.

## Why it matters

The YAML 1.2 spec says duplicate keys at the same nesting level inside
a mapping are an error, but the most widely deployed parsers
(`PyYAML.safe_load`, `gopkg.in/yaml.v2`, Ruby `Psych`) silently keep
the *last* value and drop the rest. So when an LLM is asked to "merge
these two configs" or "add a new env var to this Helm values file," it
routinely produces output where the same key appears twice and the
human reviewer reads only the first occurrence:

```yaml
env:
  LOG_LEVEL: info
  DB_URL: postgres://db/app
  LOG_LEVEL: debug          # silently overrides — ships as `debug`
```

Same failure pattern lurks in Kubernetes manifests, GitHub Actions
workflows, Docker Compose files, Ansible vars, and `pre-commit`
configs. Every one of these tools accepts the duplicate without
warning.

## How to run

```sh
python3 detect.py path/to/some_markdown.md
```

The script reads the file, finds every fenced code block whose
info-string first token (case-insensitive) is `yaml` or `yml`, and
walks each block looking for duplicate keys *within the same parent
mapping*. Findings go to stdout, summary to stderr, exit code is 1
when any finding is reported and 0 otherwise.

Each finding line is:

```
block=<N> line=<L> key=<k> first_seen_line=<L0> indent=<I>
```

where `line` and `first_seen_line` are 1-indexed line numbers in the
original markdown file, not in the YAML block.

## Expected behavior on the worked examples

```
$ python3 detect.py examples/bad.md
block=1 line=8 key=name first_seen_line=6 indent=0
block=2 line=21 key=LOG_LEVEL first_seen_line=19 indent=8
block=3 line=32 key=name first_seen_line=30 indent=4
block=4 line=45 key=baz first_seen_line=44 indent=0
total_findings=4 blocks_checked=4
$ echo $?
1

$ python3 detect.py examples/good.md
total_findings=0 blocks_checked=4
$ echo $?
0
```

So `bad.md` produces **4 findings** across 4 YAML blocks (one duplicate
per block: top-level, nested env, sequence-of-mappings entry,
post-`---` doc), and `good.md` produces **0 findings** even though the
two files have the same overall structure — the difference is solely
whether any key is repeated.

## What is in scope

* Block-style mappings (the dominant style in real config files).
* Nested mappings — duplicates are scoped to their parent mapping.
* Sequence items that are themselves mappings (`- key: value` followed
  by `  key: value`); each `- ` opens a fresh mapping scope.
* Multi-document streams: `---` resets the scope, so the same key
  appearing in two different docs is not flagged, but a duplicate
  *inside* the second doc is.

## What is out of scope (deliberately)

* Flow-style mappings (`{a: 1, a: 2}`) — rare in hand-edited config
  and would require a real tokenizer.
* Anchors / aliases / merge keys (`<<:`).
* Quoted keys that contain literal colons or escapes.
* Type-comparison or value-comparison of duplicate keys.

This is a first-line sniff test, not a YAML 1.2 conformance checker.
The bias is toward *no false positives on hand-written config* at the
cost of missing a few exotic cases.
