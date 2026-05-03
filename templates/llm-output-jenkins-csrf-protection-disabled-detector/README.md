# llm-output-jenkins-csrf-protection-disabled-detector

Stdlib-only Python detector that flags Jenkins configurations which
**disable CSRF crumb protection**. Jenkins enables this by default
since 2.222 / LTS 2.176. Turning it off makes every authenticated
POST endpoint — script-console, plugin install, job-create,
build-trigger — vulnerable to drive-by browser CSRF, escalating
ordinary "Read" sessions into full code execution on the controller.

Maps to:

- **CWE-352**: Cross-Site Request Forgery
- **OWASP A01:2021** — Broken Access Control (CSRF subcategory)
- Jenkins Security: CSRF protection is a baseline hardening flag

## What we flag

Outside `#` / `//` / `;` / `<!-- -->` comments:

1. JVM flag:
   `-Dhudson.security.csrf.GlobalCrumbIssuerConfiguration.DISABLE_CSRF_PROTECTION=true`
2. Groovy / Script Console call: `*.setCrumbIssuer(null)`.
3. JCasC YAML: `crumbIssuer: null` / `crumbIssuer: ~` /
   `crumbIssuer: "none"`.
4. Older controller-config form: `enableCSRF: false`.
5. Hudson-lineage XML: `<useCrumbs>false</useCrumbs>`.
6. Explicit XML removal: `<crumbIssuer class="none"/>`.

Each occurrence emits one finding line.

## What we accept (no false positive)

- Default JCasC: `crumbIssuer:` followed by a real
  `defaultCrumbIssuer:` block with `excludeClientIPFromCrumb: false`.
- `<crumbIssuer class="hudson.security.csrf.DefaultCrumbIssuer">` in
  `config.xml`.
- Documentation describing the disabling flag inside comments.

## Why LLMs do this

When a generated Jenkinsfile or programmatic-API client hits
`No valid crumb was included in the request`, the path of least
resistance is "turn CSRF off". Models reach for
`setCrumbIssuer(null)` or the `DISABLE_CSRF_PROTECTION=true` flag
because both are one-line fixes that immediately make the failing
script run. This detector catches the regression at PR / CI time.

## Usage

```bash
python3 detect.py path/to/jenkins-config
python3 detect.py jenkins.yaml init.groovy.d/
```

Exit `0` if clean, `1` if any findings, `2` on usage error.

## Worked example

`smoke.sh` runs the detector against `examples/bad/` (4 fixtures, all
must hit) and `examples/good/` (3 fixtures, none must hit).
