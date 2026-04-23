# Template: Conservative Implementer agent profile

A drop-in agent profile that codifies "conservative implementer" behavior. Compatible with spec-kitty agent profiles, opencode `AGENTS.md` overrides, and claude-code role prompts.

## Purpose

Most coding agents, by default, behave like enthusiastic interns: they refactor adjacent code, rename variables they don't like, add libraries they prefer, and sometimes "fix" things that weren't broken. This is fine in greenfield work. It is **catastrophic** in unfamiliar codebases or repos with strict review culture, where a 200-line surprise diff gets rejected on sight.

This profile installs the opposite default: **the agent does the minimum thing the user asked for, no more, and explicitly surfaces any assumption it had to make.**

## What it codifies

- Smallest possible diff that satisfies the requirement.
- No drive-by refactors, renames, or formatting changes.
- No new dependencies without explicit approval.
- Test coverage is preserved or improved — never reduced.
- Every assumption is stated explicitly in the response, not buried in code.
- When the agent is uncertain between two reasonable approaches, it asks instead of guessing.

The actual profile lives in [`profile.md`](profile.md). Drop it into your agent's profile directory (e.g. `.spec-kitty/profiles/`, `~/.claude/profiles/`, your opencode profile path).

## When to use

- Working in **unfamiliar codebases** where you don't know which conventions are load-bearing.
- Repos with **strict review culture** — small, focused PRs only.
- **Production / mature** codebases where surprise refactors carry real risk.
- Teams where the human reviewer is not the same person who prompted the agent.

## When NOT to use

- **Prototyping** — the friction kills exploration speed.
- **Greenfield projects** where you're establishing conventions, not respecting them.
- **Tight personal loops** where you're both the prompter and the only reviewer.
- **Migrations and refactors** — those need the *opposite* profile (broad, sweeping changes by design).

## Adapt this section

The profile in `profile.md` is generic. To tune it for your project, consider editing:

- The **diff-size soft cap** in the boundaries section (default: 100 LoC added/removed per turn).
- The **dependency policy** — currently "ask before adding"; you might prefer "never add" or "only from this allow-list".
- The **assumption-surfacing format** — the default is a `## Assumptions` section in the response; some workflows prefer inline code comments.
