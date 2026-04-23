# Contributing

Thanks for considering a contribution. This repo is a catalog of small, focused, opinionated templates. The bar is "would another engineer benefit from copying this directly into their project?" — not "is this clever?".

## PR checklist

Every PR must:

- [ ] Add **one** template (no multi-template PRs).
- [ ] Live under `templates/<short-kebab-name>/`.
- [ ] Include a `README.md` following the structure below.
- [ ] Include at least one runnable or copy-pasteable example file.
- [ ] Pass the no-internal-info check (see below).
- [ ] Update the catalog table in the root `README.md`.
- [ ] Add a one-line entry to `CHANGELOG.md` under the next unreleased version.

## Template structure

A template directory must contain:

```
templates/<name>/
  README.md          # required
  <example file(s)>  # required: at least one
  prompts/           # optional: agent prompts, if applicable
```

The `README.md` must contain these sections in this order:

1. **Title** — `# Template: <descriptive name>`
2. **Purpose** — what this template does, in one paragraph.
3. **When to use** — bullet list of fitting situations.
4. **When NOT to use** — bullet list of misfits. Equally important.
5. **Inputs / Outputs** — if applicable.
6. **Steps / How it works** — walk-through.
7. **Adapt this section** — explicit list of variables a user must change.
8. **Safety notes** — if the template touches anything irreversible.

## Naming conventions

- Directory names: `<category>-<distinctive-noun>`. Categories so far: `spec-kitty-mission-`, `agent-profile-`, `opencode-plugin-`. Add a new category only if no existing one fits.
- File names inside templates: lowercase, kebab-case, with `.example.` infix for files meant to be copied and edited (e.g. `mission.example.yaml`, `plugin.example.js`).

## No-internal-info rule

Templates must be **portable to any project**. Do not include:

- Employer or company names
- Internal codenames or product names
- Private endpoints, hostnames, or repo paths
- Personal handles other than as obvious placeholders (e.g. `your-handle`)
- Credentials, tokens, or secrets — even fake-looking ones (use clearly-fake values like `EXAMPLE_TOKEN`)

When in doubt, replace with `<placeholder>` and document it in the **Adapt this section**.

## Tone

- Direct, kind, specific.
- No marketing language.
- No emoji unless functionally necessary.
- Cite line numbers when reviewing PRs: `path/to/file:42`.
