# Template: Pre-push guardrail (generalized)

A `git push`-time safety net that **scans every new commit before it
leaves your machine** and blocks the push if it contains:

1. Strings from a configurable employer/org blacklist (internal repo
   names, internal hostnames, project codenames).
2. Common secret patterns (API keys, private-key blocks, tokens).
3. Forbidden file extensions / names (`.env`, `.pem`, `.npmrc`, …).
4. Oversized blobs (>5 MB by default).
5. Offensive-security artifact fingerprints (payload-kit repos, exploit
   kits) — opt-in.

Designed for individuals who push to **public** repos under a personal
account on a machine that **also** has work code on it. The threat
model is "I or my agent accidentally `git add .`'d something I should
not have."

## Why a pre-push hook (not pre-commit)

- Pre-commit fires on every `git commit` — including local junk
  commits. Noisy.
- Pre-push fires once per `git push`. It scans the whole commit range
  about to leave the machine.
- If you reset/squash before pushing, only the final shape is scanned.
- Crucially, pre-push **fires after** any agent has finished writing
  and committing on its own. Even fully-automated agent workflows
  cannot bypass it without explicit `--no-verify`, which you can
  forbid in agent configs.

## When to use

- You have **personal OSS work** on a machine that also has **work
  code** on it.
- You run AI coding agents that can `git commit` and `git push`
  autonomously (and you want a final sanity check).
- You publish to a **specific account/org** and want to enforce
  policy only there, leaving other remotes untouched.

## When NOT to use

- The repo is private and the threat model is purely "secret leakage"
  — `git-secrets`, `gitleaks`, or `trufflehog` in CI are more
  comprehensive.
- You're on a fully-isolated dev machine — there's nothing to leak.
- You need **server-side** enforcement (a hook on disk can be bypassed
  with `--no-verify`). Pair this with branch-protection rules in the
  forge, or with a server-side hook on a self-hosted git server.

## Anti-patterns

- **Symlinking to a path inside `.git/`.** That path is per-clone and
  not version-controlled. Symlink from `.git/hooks/pre-push` → a file
  outside the repo (or to a tracked file) so the hook survives
  `rm -rf .git`-style mistakes and is shared across clones.
- **Adding patterns without testing them.** Every regex you add can
  false-positive on legitimate code. Add one pattern at a time, run
  the test harness, then commit the pattern.
- **Making the hook too clever.** It runs on every push; if it takes
  10 seconds, people will start using `--no-verify`. Keep the scan
  bounded (last 200 commits on new branches; full range on existing
  branches) and the regex set tight.
- **Putting the blacklist of internal codenames into a public repo's
  source.** That defeats the purpose. Keep the blacklist either in a
  `~/.config/` file or in a private companion repo. The hook should
  source it.
- **Treating the hook as the only line of defense.** It catches
  obvious mistakes. It does not stop deliberate exfiltration, encoded
  content, or content the agent paraphrased. Pair with codeowners,
  required reviews, and forge-level secret scanning.

## Files

- `pre-push.sh` — the generalized hook. Reads `guardrail.config.sh`
  for the per-user pattern lists.
- `guardrail.config.example.sh` — example config with placeholder
  patterns. Copy to `~/.config/guardrail/guardrail.config.sh`,
  edit, never commit your real one to a public repo.
- `install.sh` — symlinks the hook into a target repo's
  `.git/hooks/pre-push`.
- `test/test-guardrail.sh` — end-to-end test that builds a throwaway
  repo, makes commits that should and should not trip each block,
  and asserts the right outcome.
- `examples/sample-block-output.md` — what a real block looks like in
  the terminal, for each of the five blocks.

## How it works

The hook runs in the standard `git pre-push` context: stdin is the
list of refs being pushed, args 1+2 are remote name and URL. It:

1. Checks the URL against a per-user **scope filter** (default: only
   enforce when pushing to `github.com/<your-account>/`). All other
   remotes pass through.
2. Resolves the commit range about to be pushed (bounded to 500
   commits / 200 on a brand-new branch, to keep it fast).
3. For each commit, runs five passes:
   - **Block 1** — internal-string blacklist (your codenames).
   - **Block 2** — secret-pattern blacklist (provider API keys,
     private-key headers).
   - **Block 3** — forbidden-filename blacklist.
   - **Block 4** — oversized-blob check (>5 MB).
   - **Block 5** — opt-in offensive-security fingerprint check.
4. On any hit, prints a structured `[guardrail BLOCK]` line and exits
   non-zero. Push is aborted client-side.

## Adapt this section

- `SCOPE_FILTER` — defaults to `github.com/<your-account>/`. Change
  to your forge + account.
- `INTERNAL_PATTERNS` — your employer's repo names, codenames,
  internal domains. Keep this list **outside** the public repo.
- `MAX_BLOB_BYTES` — defaults to 5 MB.
- `ENABLE_BLOCK_5_ATTACK_PATTERNS` — defaults to `1`. Set to `0` if
  you legitimately work on offensive-security tooling and the false
  positives outweigh the safety.
- `MAX_COMMITS_SCANNED` — defaults to 500 / 200 on new branches.

## Bypass policy

The hook can be bypassed with `git push --no-verify`. That is **by
design** — you may need it for legitimate reasons (re-pushing a
previously-scanned commit, recovering from a stuck push). To prevent
agents from bypassing:

- Audit your agent configs (`AGENTS.md`, `CLAUDE.md`, opencode
  config) to forbid `--no-verify` in the bash tool's allowed
  commands.
- Add a server-side check (forge branch protection, required
  pre-merge job) for the same patterns. The hook is convenience;
  forge-side is policy.
