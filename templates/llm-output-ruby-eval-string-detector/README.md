# llm-output-ruby-eval-string-detector

Pure-stdlib python3 single-pass scanner that flags Ruby string-form
`eval`, `instance_eval`, `class_eval`, `module_eval`, and
`binding.eval` calls.

## What it detects

Ruby's `Kernel#eval` and the `*_eval` family on `Module` / `Object`
accept either a **String** or a **Block**. The block form is just a
closure — fine. The string form re-parses the argument as Ruby source
code at runtime, with the same blast radius as `system($USER_INPUT)`
when any piece is attacker-controlled.

LLM-emitted Ruby reaches for `eval "Foo.new.#{name}"` or
`klass.class_eval(snippet)` to "build a method dynamically." That is
almost always wrong. The safe, idiomatic replacements:

| Anti-pattern                                 | Safe alternative                       |
| -------------------------------------------- | -------------------------------------- |
| `class_eval("def #{name}; ...; end")`        | `define_method(name) { ... }`          |
| `eval("foo.#{m}")`                           | `foo.public_send(m)`                   |
| `eval("@#{n}")`                              | `instance_variable_get(:"@#{n}")`      |
| `instance_eval("@x = #{v}")`                 | `instance_variable_set(:@x, v)`        |

The detector also catches `binding.eval(...)`,
`TOPLEVEL_BINDING.eval(...)`, and `Kernel.eval(...)` /
`Kernel#eval(...)`.

## What gets scanned

* Files with extension `.rb`, `.rake`, `.gemspec`, `.ru`.
* `Rakefile`, `Gemfile`, `Guardfile`, `Capfile`.
* Files whose first line is a `ruby` shebang.
* Directories are recursed.

## Block form is NOT flagged

```ruby
obj.instance_eval do      # <- block, safe, NOT flagged
  @x = compute
end

klass.class_eval { ... }  # <- block, safe, NOT flagged
```

The detector inspects the first non-space token after the call. If it
is `do` or `{`, the call is treated as block-form and skipped.

## False-positive notes

* `eval` inside a `#` comment or a `"..."` / `'...'` / backtick
  string literal is masked before scanning, so the only thing that
  can match is an actual call site.
* A method NAMED `evaluate`, `eval_log`, `myeval`, etc. is NOT
  flagged — the regex requires the exact word boundary on
  `eval` / `instance_eval` / `class_eval` / `module_eval`.
* `# eval-ok` on a line suppresses that line entirely. Use it for
  audited literal-only calls.
* The detector does NOT try to prove a string is constant. Even
  `eval("1 + 1")` would be flagged — add `# eval-ok` if intentional.
* Out of scope (separate detectors): `Object#send` /
  `public_send`, `ERB.new(src).result(binding)`,
  `define_method` with a block.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: ruby-eval-string — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad.rb
examples/bad.rb:4:1: ruby-eval-string — eval "puts #{user_input}"                              # 1: double-quoted interpolation into eval
examples/bad.rb:5:1: ruby-eval-string — eval('puts ' + cmd)                                    # 2: concatenated string into eval()
examples/bad.rb:6:1: ruby-eval-string — instance_eval "@x = #{value}"                          # 3: instance_eval with a string
examples/bad.rb:7:1: ruby-eval-string — klass.class_eval("def #{name}; #{body}; end")          # 4: class_eval with a string
examples/bad.rb:8:1: ruby-eval-string — Mod.module_eval(snippet)                               # 5: module_eval with a bareword (likely-string var)
examples/bad.rb:9:1: ruby-eval-string — binding.eval(expr)                                     # 6: binding.eval on a variable
examples/bad.rb:10:1: ruby-eval-string — Kernel.eval %q{system("rm -rf /")}                     # 7: %q literal into Kernel.eval
examples/bad.rb:11:1: ruby-eval-string — TOPLEVEL_BINDING.eval("$LOAD_PATH << dir")             # 8: literal into TOPLEVEL_BINDING.eval
examples/bad.rb:12:1: ruby-eval-string — eval `cat /tmp/payload.rb`                             # 9: backtick command output into eval
examples/bad.rb:13:1: ruby-eval-string — obj.instance_eval(<<~RUBY)                             # 10: heredoc into instance_eval
# 10 finding(s)

$ python3 detect.py examples/good.rb
# 0 finding(s)
```

bad: **10** findings, good: **0** findings.
