# llm-output-fish-source-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous,
dynamic** invocations of the fish-shell `source` (and its alias `.`)
builtin in `*.fish` files (and any file with a `#!.../fish` shebang).

Fish's `source` reads a file and executes its contents in the current
shell. When the path argument is built from a variable, a command
substitution `(cmd ...)`, or a here-string-style construct, an
attacker who controls that value gains arbitrary fish-script
execution: env mutation, function redefinition, external command
launch, etc. LLMs frequently emit `source (curl -L $url | psub)` for
"install this remote config" snippets — exactly the shape this
scanner exists to catch. A literal `source ~/.config/fish/aliases.fish`
(no `$`, no `(`) is **not** flagged. Suppress an audited line with a
trailing `# source-ok` comment.
