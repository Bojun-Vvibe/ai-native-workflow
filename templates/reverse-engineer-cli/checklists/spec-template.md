# Behavior spec template

Copy this skeleton, rename to `<cli-name>-behavior-spec.md`, and
fill from your probe checklists. Keep it in git next to your
automation; diff on each CLI version bump.

---

# `<cli-name>` behavior spec

- **Version probed:** `<output of <cli> --version>`
- **Date probed:** YYYY-MM-DD
- **Probe environment:** macOS 14.x / zsh 5.9 / en_US.UTF-8 (etc.)
- **Probed by:** name + methodology version
- **Source available?** no / yes-but-not-read / yes-and-cross-checked

## 1. Surface (command tree)

```
<cli>
├── <sub1>           — one-line description
│   ├── <leaf1.1>    — ...
│   └── <leaf1.2>    — ...
├── <sub2>
│   └── <leaf2.1>
└── <sub3>
```

Global flags (apply to all subcommands):

| flag | type | default | description | source |
|---|---|---|---|---|
| `--config <path>` | path | `~/.<cli>rc` | override config file | `--help` + observed |
| `--json` | bool | false | machine-readable output | observed (undocumented) |
| `--debug` | bool | false | log every internal step to stderr | binary strings |

## 2. Per-command behavior

For each leaf command, one section:

### `<cli> <leaf>`

**Synopsis:** `<cli> <leaf> [--flag-a <v>] [--flag-b] <positional>`

**Inputs:**
- positional: `<name>` (required, type, validation rules)
- `--flag-a <v>`: type, default, semantics
- `--flag-b`: type, default, semantics

**Behavior:**
- One-paragraph description of what the command does, in
  observable terms (not "internally it..."), e.g. "Reads
  `<positional>` line by line, applies <transform>, writes
  result to stdout."

**Output (success):**
- stdout: format + schema
- stderr: empty
- exit code: 0
- side effects: none / list

**Output (success with `--json`):**
- stdout schema:
  ```json
  { "field": "type", ... }
  ```

**Failure modes:**

| trigger | exit code | stderr substring | side effects |
|---|---|---|---|
| missing `<positional>` | 2 | `error: required argument` | none |
| invalid path | 1 | `cannot open` | none |
| network down | 4 | `connection refused` | none |
| ... | ... | ... | ... |

**Determinism:** ___ (deterministic / non-deterministic in `field X`)

**Idempotency:** ___ (safe to retry / not safe — describe)

**Observed quirks:** ___

## 3. Configuration

**Config file lookup order** (first-match-wins):
1. `--config` flag
2. `$XDG_CONFIG_HOME/<cli>/config.toml`
3. `~/.config/<cli>/config.toml`
4. `~/.<cli>rc`

**Config schema** (toml/yaml/json):
```toml
[section]
key = "type, default, semantics"
```

**Required fields:** ___
**Optional fields:** ___

## 4. Environment variables

| var | type | default | semantics | precedence vs flag |
|---|---|---|---|---|
| `<CLI>_TOKEN` | string | none | auth token | flag wins |
| `<CLI>_PROFILE` | string | `default` | named config section | env wins |
| `NO_COLOR` | bool | false | disable ANSI color | n/a (always wins) |

## 5. State / cache

- Directory: ___
- Files: ___
- Format: ___
- Cleanup policy: ___ (TTL / never / on `<cli> clean`)

## 6. Quirks & non-obvious behaviors

Numbered list. Each item should describe a behavior that surprised
the prober and explain when it matters.

1. ___
2. ___

## 7. Things tested but not fully determined

Be honest. Don't pretend.

1. ___
2. ___

## 8. Things deliberately not tested

With reason (irreversible / requires production / out of scope).

1. ___

## 9. Spec maintenance

- **Re-probe trigger:** new `<cli> --version` output, or one of
  these failure modes appears in production: ___
- **Probe checklists archived at:** ___
- **Last diff against previous spec:** ___
