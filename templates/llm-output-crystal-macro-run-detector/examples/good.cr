# GOOD: no compile-time `run` / `system` / backtick sites. The
# detector must NOT flag any of these constructs.

module Good
  # Normal runtime Process.run — not a macro, ignored.
  def run_uname
    Process.run("uname", ["-a"])
  end

  # Runtime backtick — outside macro brackets, ignored.
  def head_sha
    `git rev-parse HEAD`.strip
  end

  # String literal that *contains* `{{ run("evil") }}` as prose.
  DOC = "see also: {{ run(\"evil\") }} discussion in macro guide"

  # Comment that mentions {{ run("evil") }} must not trigger.
  # Even nested: {% sys = `cmd` %}

  # Macro interpolation that does NOT call run/system/backtick.
  TYPE_NAME = {{ @type.name.stringify }}

  # Suppressed line: an audited compile-time codegen step.
  CODEGEN = {{ run("./helpers/audited") }} # macro-run-ok
end
