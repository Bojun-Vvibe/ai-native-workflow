# llm-output-rust-command-shell-tainted-detector

Stdlib-only Python detector that flags **Rust** source where
`std::process::Command` (or its `tokio::process::Command` re-export)
spawns a shell interpreter (`sh`, `bash`, `zsh`, `dash`, `ksh`,
`cmd`, `cmd.exe`, `powershell`, `pwsh`) with `-c` / `/C` and a script
argument that is *runtime-built* — `format!`, a bare ident, a string
concatenation, `String::from`, `.to_string()`, etc.

This is the canonical CWE-78 (OS Command Injection) shape in Rust.
A LLM under "make subprocess work" pressure tends to write:

```rust
Command::new("sh")
    .arg("-c")
    .arg(format!("ls -la {}", user_path))   // injection
    .output()?;
```

instead of the safe shapes:

```rust
// argv form: no shell at all
Command::new("ls").arg("-la").arg(user_path).output()?;

// shell with positional arg ($1 inside the script):
Command::new("sh").arg("-c").arg("ls -- \"$1\"").arg("sh").arg(user).output()?;
```

## Why this exact shape

Rust's `Command` *does not* go through a shell unless you ask it to.
Asking for a shell almost always means "I want word-splitting + glob",
which is the same as asking for injection when the command string
mixes static text and untrusted input. The fix is to either:

* drop the shell entirely (argv form), or
* keep the script body *static* and pass user data as positional args.

The detector enforces the second discipline by flagging any
`Command::new("<shell>")` chain whose `.arg("-c")` (or `.arg("/C")`)
is followed by a non-literal `.arg(...)`.

## What's flagged

1. **`rust-command-shell-tainted`** — `Command::new("sh"|"bash"|...)`
   chain with `.arg("-c")` (or `.arg("/C")`) where the **next**
   `.arg(...)` is not a plain string literal. Bare idents, `format!`,
   `String::from`, `.to_string()`, `&s`, `s + ...` are all treated as
   runtime-built.
2. **`rust-command-shell-arg-format`** — any `.arg(format!(...))`
   chained onto a shell-program `Command`, even without `-c` (covers
   `powershell -Command` patterns where the script slot has a
   different name).

Suppress with a trailing `// llm-allow:rust-command-shell` on the
relevant `.arg(...)` line or anywhere within the same statement.

## Safe shapes the detector deliberately leaves alone

* Argv form — `Command::new("ls").arg(user).output()?;`
* Shell with a literal script — `.arg("-c").arg("date -u")`
* Shell with `concat!("...","...")` of all-literal arms
* Positional-arg pattern — `.arg("-c").arg("ls -- \"$1\"").arg("sh").arg(user)`

## CWE / standards

- **CWE-78**: Improper Neutralization of Special Elements used in an
  OS Command ('OS Command Injection').
- **OWASP A03:2021** — Injection.
- Closely related to GHSA advisories on Rust crates that wrap
  subprocess invocations (`shell-words`, `duct`, etc.).

## Limits / known false negatives

- We don't follow let-bindings: `let s="sh"; Command::new(s)...` is not
  flagged. (Most LLM output uses the literal directly.)
- We don't understand cross-function tainting; if your runtime-built
  script is constructed in another function and passed in, we still
  flag the call site (which is the correct place to fix it anyway).
- `std::process::Command::new(env!("SHELL")).arg("-c").arg(x)` is
  flagged only if `env!("SHELL")` is replaced by a literal at the
  call site — `env!` is *not* a literal here.

## Usage

```bash
python3 detect.py path/to/file.rs
python3 detect.py path/to/dir/   # walks *.rs, *.md, *.markdown
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Verify

```
$ bash verify.sh
bad=6/6 good=0/6
PASS
```

### Worked example — `python3 detect.py examples/bad/`

```
$ python3 detect.py examples/bad/
examples/bad/01_sh_dash_c_format.rs:4: rust-command-shell-tainted: Command::new('"sh"') ... -c with runtime-built script (CWE-78): Command::new("sh")
examples/bad/02_bash_dash_c_ident.rs:4: rust-command-shell-tainted: Command::new('"bash"') ... -c with runtime-built script (CWE-78): Command::new("bash")
examples/bad/03_binsh_dash_c_ident.rs:5: rust-command-shell-tainted: Command::new('"/bin/sh"') ... -c with runtime-built script (CWE-78): Command::new("/bin/sh").arg("-c").arg(cmd).output()?;
examples/bad/04_powershell_format.rs:4: rust-command-shell-arg-format: Command::new('"powershell.exe"') with .arg(format!(...)) (CWE-78): Command::new("powershell.exe")
examples/bad/05_cmd_slashc_format.rs:4: rust-command-shell-tainted: Command::new('"cmd"') ... -c with runtime-built script (CWE-78): Command::new("cmd")
examples/bad/06_tokio_zsh_format.rs:5: rust-command-shell-tainted: Command::new('"zsh"') ... -c with runtime-built script (CWE-78): Command::new("zsh").arg("-c").arg(line).output().await?;
$ echo $?
1
```

### Worked example — `python3 detect.py examples/good/`

```
$ python3 detect.py examples/good/
$ echo $?
0
```

Layout:

```
examples/bad/
  01_sh_dash_c_format.rs        # sh -c format!("ls -la {}", user_path)
  02_bash_dash_c_ident.rs       # bash -c <bare ident>
  03_binsh_dash_c_ident.rs      # /bin/sh -c <built var>
  04_powershell_format.rs       # powershell.exe -Command format!(...)
  05_cmd_slashc_format.rs       # cmd /C format!("dir {}", name)
  06_tokio_zsh_format.rs        # tokio Command zsh -c <built var>
examples/good/
  01_argv_form.rs               # Command::new("ls").arg(...) — no shell
  02_sh_dash_c_literal.rs       # sh -c "date -u" — static script
  03_sh_positional_arg.rs       # sh -c "ls -- \"$1\"" sh user — safe pattern
  04_direct_exec_git.rs         # Command::new("git").args([...])
  05_bash_concat_macro.rs       # bash -c concat!("a"," && ","b") — static
  06_suppressed.rs              # explicit // llm-allow:rust-command-shell
```
