# Integrating the guardrail with opencode

This doc shows how to wire `plugin.example.js` into opencode's plugin system
so the guardrail runs automatically before any agent-suggested `git commit`.

> opencode's plugin and hook surface evolves between releases. The shape below
> reflects the model used by recent versions: a `~/.config/opencode/` directory
> with a `package.json` and a `plugin/` subdirectory that exports plugin
> objects. Adapt paths if your version differs. Always cross-check against
> [opencode's docs](https://opencode.ai/docs).

## 1. Drop the plugin into your opencode plugin directory

```
~/.config/opencode/
├── package.json
└── plugin/
    └── pre-commit-guardrail.js   <-- copy of plugin.example.js
```

If you don't already have `~/.config/opencode/`, create it. The `package.json`
only needs `{"type": "commonjs"}` for the example as-shipped (the plugin uses
`require`); switch to ES modules if your other plugins are ESM.

## 2. Register the plugin

Depending on your opencode version, the plugin may be auto-loaded from the
`plugin/` directory, or you may need an explicit entry in your opencode
config. Two common shapes:

**Auto-load (newer versions)**: nothing to do beyond placing the file. opencode
discovers exports under `~/.config/opencode/plugin/`.

**Explicit registration**: in your opencode config (`~/.config/opencode/config.json`
or equivalent), add:

```json
{
  "plugins": [
    "./plugin/pre-commit-guardrail.js"
  ]
}
```

Restart opencode after either change.

## 3. Verify the hook fires

The plugin registers `hooks["before:git-commit"]`. To confirm the hook is
loaded, run a test commit in a scratch directory:

```bash
mkdir /tmp/guardrail-smoke && cd /tmp/guardrail-smoke
git init -q
echo 'apiKey = "sk-test-fake-not-real-1234"' > config
git add config
# Ask opencode to commit. The guardrail should refuse.
```

If opencode commits anyway, the hook is not loaded. Check the plugin
directory path, restart opencode, and re-test.

## 4. Bypass mechanism (use sparingly)

The plugin honors a `GUARDRAIL_BYPASS=i-am-sure` env var for one-shot bypass.
Don't put this in your shell rc. Use it only inline for a specific commit
where you've manually verified the diff:

```bash
GUARDRAIL_BYPASS=i-am-sure git commit -m "intentional: vendored test fixtures"
```

Document any bypass in the commit message. If you find yourself bypassing
often, the rules are wrong — tune them, don't route around them.

## 5. Composing with other guardrails

If you also use a server-side check (GitHub secret scanning push protection,
or a repo-level pre-push hook like the one in [Bojun-Vvibe/.guardrails](https://github.com/Bojun-Vvibe)),
this plugin is the *first* line of defense, not the only one. The chain looks
like:

```
agent intent → opencode plugin (this) → local pre-commit hook → server-side push protection
```

Each layer catches what earlier layers missed. The opencode plugin is the
fastest feedback loop because it tells the *agent* "no" before the commit
even exists, instead of telling the human "no" after the fact.

## 6. Common pitfalls

- **The plugin sees `git diff --staged`, not your editor buffer.** If the
  agent writes a secret to a file but doesn't `git add` it, this plugin
  doesn't see it. The repo-level pre-commit / pre-push hook is the backstop.
- **Regex tuning is project-specific.** The default patterns are
  conservative. Add patterns for your project's custom token shapes; over
  time you'll prevent more incidents.
- **Don't disable the plugin to fix a noisy match.** Tighten the regex
  instead. A disabled guardrail is the same as no guardrail.
