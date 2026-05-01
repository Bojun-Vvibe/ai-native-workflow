# llm-output-dockerfile-add-remote-url-detector

Stdlib-only Python detector that flags **Dockerfile** instructions of
the form

```
ADD https://example.com/payload.tgz /opt/payload.tgz
```

— i.e. `ADD` with a remote `http://`, `https://`, or `ftp://` source
and **no** `--checksum=` flag. This pattern is called out as an
anti-pattern by Docker's own best-practices guide and maps to
**CWE-494: Download of Code Without Integrity Check**: the build
fetches a remote payload over the network, expands it into the image,
and never verifies what it got.

LLMs reach for `ADD <url>` constantly because it is one line shorter
than the safe equivalent (`RUN curl -fsSL ... && sha256sum -c ...`).

## Heuristic

For each **logical** Dockerfile line (after joining `\`-continuations
and skipping `#` comment lines):

1. Match `^\s*ADD\b` (case-insensitive, per Dockerfile rules).
2. Find any token of the form `(?:https?|ftp)://...`.
3. If `--checksum=...` is present on the same logical line, **accept**
   it (BuildKit verifies integrity in this case).
4. Otherwise, emit a finding.

We deliberately scope to `ADD` only:

- `COPY` rejects URLs at parse time, so it can't carry this bug.
- `RUN curl|wget` is a separate, more contextual problem and is
  covered by other detectors in this series.

## CWE / standards

- **CWE-494**: Download of Code Without Integrity Check.
- **CWE-829**: Inclusion of Functionality from Untrusted Control Sphere.
- **OWASP A08:2021** — Software and Data Integrity Failures.
- Docker docs: "Best practices for writing Dockerfiles" — *Use COPY
  instead of ADD* and *prefer RUN curl with checksum verification*.

## What we accept (no false positive)

- `COPY ./local /dest` — local source.
- `ADD ./local.tgz /opt/` — local source, even tarballs.
- `ADD --checksum=sha256:... https://... /dest` — integrity-checked.
- `RUN curl ... && sha256sum -c -` — out of scope for this detector.
- URLs inside `#` comments — not instructions.

## What we flag

- `ADD https://...`, `ADD http://...`, `ADD ftp://...`
- `ADD --chown=...:... https://...` (chown does not add integrity)
- `ADD \` followed by URL on the next line (continuation)
- Mixed-case `Add`, `add` (Dockerfile is case-insensitive)

## Limits / known false negatives

- We do not resolve `ARG`-substituted URLs:
  `ARG URL=https://...; ADD ${URL} /dest` parses as `ADD ${URL} /dest`
  and slips past us. Resolving build args would require a full
  Dockerfile evaluator.
- We do not flag URLs reached via shell expansion inside `RUN`.

## Usage

```bash
python3 detect.py path/to/Dockerfile
python3 detect.py path/to/dir/   # walks Dockerfile, *.Dockerfile, Dockerfile.*, *.dockerfile
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
  01_https.Dockerfile          # plain ADD https://
  02_http.Dockerfile           # plain ADD http://
  03_ftp.Dockerfile            # ADD ftp://
  04_chown_remote.Dockerfile   # --chown does not save you
  05_continuation.Dockerfile   # multi-line ADD with URL
  06_mixed_case.Dockerfile     # `Add` instruction
examples/good/
  01_copy_local.Dockerfile             # COPY local
  02_add_local_tar.Dockerfile          # ADD local tgz
  03_run_curl_with_checksum.Dockerfile # RUN curl + sha256sum -c
  04_add_with_checksum.Dockerfile      # ADD --checksum=sha256:...
  05_add_local_dir.Dockerfile          # ADD local dir w/ continuation
  06_url_in_comment.Dockerfile         # URL inside # comment
```
