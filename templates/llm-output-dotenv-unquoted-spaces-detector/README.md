# llm-output-dotenv-unquoted-spaces-detector

## What it detects

`.env`-style assignments where the value contains an unescaped ASCII
space or tab and is **not** wrapped in matching single or double
quotes. Most dotenv loaders (`python-dotenv`, `godotenv`, `dotenv` on
Node, the POSIX `set -a; . ./.env; set +a` trick) silently truncate at
the first whitespace, so `DB_PASSWORD=hunter two` ends up as
`DB_PASSWORD=hunter`. This is a high-frequency LLM mistake when an
assistant is asked to "scaffold a .env" from natural-language values.

The detector is code-fence aware: triple-backtick or triple-tilde
fenced blocks toggle an "ignore" mode, so you can point it at a
markdown blob that contains a `.env` snippet without preprocessing.

## When to use

- After an LLM produces a `.env`, `.env.example`, or `env.local` file.
- In CI, against any committed dotenv file, to catch silent truncation.
- As a post-processor on assistant chat output that may contain
  fenced env blocks.

## Sample input — `example_bad.env.txt`

(Stored with a `.env.txt` suffix so repo guardrails don't flag it as a
real environment file. Pass any path to the detector — extension is
ignored.)

```env
APP_NAME=My Cool Service
DB_PASSWORD=hunter two
GREETING=hello world
LOG_LEVEL=info
export GIT_AUTHOR=Jane Doe
NOTE=plain # trailing inline comment is fine
QUOTED_OK="this has spaces but is quoted"
SINGLE_OK='also fine'
EMPTY=
```

## Sample output

```
$ python3 detector.py example_bad.env.txt
FOUND 4 finding(s):
  line 2: APP_NAME='My Cool Service' -- unquoted value for APP_NAME contains whitespace; most loaders will truncate at the first space
  line 3: DB_PASSWORD='hunter two' -- unquoted value for DB_PASSWORD contains whitespace; most loaders will truncate at the first space
  line 4: GREETING='hello world' -- unquoted value for GREETING contains whitespace; most loaders will truncate at the first space
  line 6: GIT_AUTHOR='Jane Doe' -- unquoted value for GIT_AUTHOR contains whitespace; most loaders will truncate at the first space
```

```
$ python3 detector.py example_good.env.txt
OK: no unquoted-spaces findings
```

Exit code is `1` when findings exist, `0` otherwise — drop straight
into a pre-commit hook or CI step.

## Files

- `detector.py` — pure stdlib, ~70 lines.
- `example_bad.env.txt` — triggers 4 findings.
- `example_good.env.txt` — passes cleanly.
