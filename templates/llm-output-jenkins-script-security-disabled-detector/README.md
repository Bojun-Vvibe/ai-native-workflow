# llm-output-jenkins-script-security-disabled-detector

Stdlib-only Python detector that flags **Jenkins** configurations
which disable the Script Security sandbox / approval system. Maps to
**CWE-693** (protection mechanism failure), **CWE-862** (missing
authorization), **CWE-94 / CWE-95** (eval / code injection), and
**CWE-269** (improper privilege management).

Jenkins ships with a Groovy sandbox plus an admin-approval queue
("In-process Script Approval") because Pipeline / Job DSL / Script
Console are arbitrary Groovy execution surfaces against the
controller JVM. Disabling the sandbox means anyone who can edit a
Pipeline definition (or any Job DSL seed job that ingests
user-supplied scripts) gets RCE on the Jenkins controller, which
typically holds credentials to the entire CI/CD plane.

LLMs reach for `sandbox: false` /
`-Dpermissive-script-security.enabled=true` because the most common
"why is my Pipeline failing" answer on the internet is "just turn off
script security". The fix is one line; the consequence is full
controller compromise.

## Heuristic

We flag any of the following, outside `#` / `//` comment lines:

1. `sandbox: false` (or `sandbox false`) inside Pipeline /
   Jenkinsfile / JCasC / Job DSL contexts.
2. `useScriptSecurity(false)` / `useScriptSecurity: false` in Job DSL.
3. JVM flag `-Dpermissive-script-security.enabled=true` on a `java`
   / `jenkins.war` invocation, in a systemd unit, Dockerfile
   ENV/CMD, or k8s args.
4. JCasC `approvedSignatures: ["*"]` wildcard approval.
5. XML `<useScriptSecurity>false</useScriptSecurity>` in a job
   `config.xml`.

Each occurrence emits one finding line.

## CWE / standards

- **CWE-693**: Protection Mechanism Failure.
- **CWE-862**: Missing Authorization.
- **CWE-94 / CWE-95**: Improper Control of Generation of Code / Eval
  Injection.
- **CWE-269**: Improper Privilege Management.
- Jenkins Security Advisory program: many SECURITY-* advisories cover
  bypasses of script-security; *disabling it* removes the bypass
  defenses entirely.

## What we accept (no false positive)

- `sandbox: true` (the safe default).
- Documentation / commented-out lines.
- `approvedSignatures: ["method java.lang.String length"]` (specific
  signatures, not `"*"`).
- Job XMLs that omit the element entirely (Jenkins defaults to
  `true`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        ≥3 fixtures that MUST be flagged
examples/good/       ≥3 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/Jenkinsfile
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

The Pipeline approval flow is annoying, the error messages are
opaque, and the top web answer is to disable script security. An LLM
that has trained on Stack Overflow will suggest exactly that. Catch
it in CI before it hits a controller that can deploy to prod.
