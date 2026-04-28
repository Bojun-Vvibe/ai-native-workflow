# llm-output-dockerfile-latest-tag-detector

## Problem

LLMs frequently emit Dockerfiles with `FROM image:latest` (or no tag at all,
which Docker treats as `:latest`). This is an irreproducible-build smell:
`latest` floats, so the same Dockerfile builds different images over time,
breaking reproducibility, supply-chain attestations, and rollback safety.

This detector flags `FROM` lines that:

1. Use an explicit `:latest` tag.
2. Omit the tag entirely (implicit `:latest`).

It is **code-fence aware**: when fed Markdown that embeds a Dockerfile inside
a fenced code block (```dockerfile ... ``` or ```Dockerfile ... ```), it scans
the fence body. When fed a raw Dockerfile, it scans the whole file.

Stage aliases (`AS builder`), digests (`@sha256:...`), platform flags
(`--platform=...`), and build-arg-templated tags (`${VERSION}`) are handled
sensibly — digests and `${...}` tags are treated as pinned and not flagged.

## Usage

```
python3 detector.py path/to/Dockerfile
python3 detector.py path/to/notes.md
cat Dockerfile | python3 detector.py -
```

Exit code is always `0` so the detector is safe to drop into pipelines.

## Finding format

One finding per line on stdout:

```
<path>:<line>: <code>: <message> | <offending FROM line trimmed>
```

Codes:

- `DOCKER001` — explicit `:latest` tag
- `DOCKER002` — no tag (implicit `:latest`)

A trailing summary line is printed:

```
# findings: <N>
```

## Example

```
$ python3 detector.py examples/bad.Dockerfile
examples/bad.Dockerfile:1: DOCKER001: image uses :latest tag | FROM python:latest
examples/bad.Dockerfile:5: DOCKER002: image has no tag (implicit :latest) | FROM alpine
examples/bad.Dockerfile:9: DOCKER001: image uses :latest tag | FROM node:latest AS builder
# findings: 3

$ python3 detector.py examples/good.Dockerfile
# findings: 0
```
