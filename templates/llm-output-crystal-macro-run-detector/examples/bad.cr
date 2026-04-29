# BAD: every macro-bracket here invokes a compile-time code-execution
# primitive. When the path / arguments are anything other than an
# audited literal, this gives the build attacker-controllable RCE.

module Bad
  # 1. Direct run() of an external program at compile time.
  CODEGEN = {{ run("./helpers/codegen", "User") }}

  # 2. Run with non-literal argument (env var resolved at compile time).
  CONFIG  = {{ run("./gen", env("BUILD_TAG")) }}

  # 3. Macro `system` shell-out.
  HOST = {{ system("uname -a") }}

  # 4. Backtick command inside a `{{ ... }}` interpolation.
  TAG = {{ `git rev-parse HEAD` }}

  # 5. Backtick command inside a `{% ... %}` directive.
  {% commit = `git log -1 --format=%H` %}

  # 6. Multi-line macro block with a run() inside.
  RESULT = {{
    run(
      "./helpers/render",
      "schema.json",
    )
  }}
end
