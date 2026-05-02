# llm-output-airflow-default-fernet-key-detector

Static lint that flags Apache Airflow configurations and environment
files that ship the well-known *example* Fernet key, leave the key
empty, or hard-code something that obviously did not come from a
CSPRNG.

## Background

Airflow encrypts Connection passwords and Variables marked secret
with a single symmetric Fernet key, configured at `[core] fernet_key`
in `airflow.cfg` or via `AIRFLOW__CORE__FERNET_KEY`. Anyone who holds
that key can decrypt every credential in the metadata database.

The official Airflow docs explicitly call out two failure modes:

1. **Empty key** — Airflow falls back to storing connection passwords
   in plaintext in the metadata DB.
2. **Shared / example key** — keys copy-pasted from tutorials, blog
   posts, or Stack Overflow answers can be used by anyone who reads
   the same source to decrypt your DB dump.

LLM-generated Airflow snippets routinely paste the same handful of
example keys (notably `ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=`,
which appears in countless tutorials), or leave the value as
`YOUR_FERNET_KEY` / `CHANGEME`, or invent a "key" that's just `A`
repeated 43 times followed by `=`.

## What it catches

- `fernet_key =` (empty) in `airflow.cfg`.
- `fernet_key = YOUR_FERNET_KEY` / `CHANGEME` / `REPLACE_ME` placeholders.
- Known publicly published example keys (from the upstream tutorial
  and high-traffic blog posts).
- Single-character repetition (e.g. `AAAAAAAAAAAA…=`).
- Strings that don't urlsafe-base64-decode to exactly 32 raw bytes
  (so not a real Fernet key at all).
- All-zero / all-`0xff` raw bytes.
- Same checks applied to `AIRFLOW__CORE__FERNET_KEY` env-var lines in
  shell scripts, Dockerfiles, `docker-compose.yml`, `.env`, etc.

## What it does *not* catch

This is a static check: it cannot tell whether a real-looking 32-byte
key has been reused across environments. Pair it with a secret-scanner
that tracks key reuse across repositories.

## Suppression

Add the comment marker `airflow-fernet-key-allowed` anywhere in the
file to suppress findings (intended for known-test fixtures).

## Usage

```sh
python3 detector.py path/to/airflow.cfg path/to/.env
```

Exit code is the number of findings. `0` means clean.

## Verify

```sh
bash verify.sh
```

Prints `bad=N/N good=0/M` and `PASS` when every bad fixture fires and
every good fixture is clean.
