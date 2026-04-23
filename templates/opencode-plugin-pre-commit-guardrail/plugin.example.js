// plugin.example.js
//
// Opencode plugin: pre-commit guardrail.
//
// Intercepts agent-suggested `git commit` invocations. Before the commit
// is allowed through, runs `git diff --staged` and checks the staged
// content against a set of rules (secrets, diff size, forbidden file
// extensions). If any rule trips, the commit is blocked and a structured
// refusal is returned to the agent.
//
// Drop into your opencode plugin directory and reference from your
// opencode config.

const { execSync } = require("node:child_process");

// ---- Configuration ---------------------------------------------------------

const SECRET_PATTERNS = [
  /-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----/,
  /AKIA[0-9A-Z]{16}/,                          // AWS access key id
  /\bxox[baprs]-[A-Za-z0-9-]{10,}/,            // Slack-style token shape
  /ghp_[A-Za-z0-9]{30,}/,                       // GitHub personal access token shape
  /gh[osu]_[A-Za-z0-9]{30,}/,                   // other GitHub token shapes
  /\bey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b/, // JWT-shaped
  /\b[Aa]uthorization\s*[:=]\s*['"]?[Bb]earer\s+[A-Za-z0-9._-]{20,}/,
  /\bsk-(?:test-|live-|proj-)?[A-Za-z0-9-]{16,}/,  // OpenAI / OpenAI-style key shape (hyphen-tolerant)
];

const FORBIDDEN_EXTENSIONS = [
  ".env", ".pem", ".key", ".p12", ".pfx", ".mobileprovision", ".keystore",
];

const MAX_ADDED_LINES = 1000;
const BYPASS_ENV_VAR = "GUARDRAIL_BYPASS";
const BYPASS_VALUE = "i-am-sure";

// ---- Rules -----------------------------------------------------------------

const RULES = [
  function checkSecrets(diffText) {
    const hits = SECRET_PATTERNS.filter((p) => p.test(diffText));
    return hits.length === 0
      ? { violated: false }
      : { violated: true, message: `secret-shaped strings detected (${hits.length} pattern(s) matched)` };
  },
  function checkDiffSize(diffText) {
    const added = diffText.split("\n").filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
    return added <= MAX_ADDED_LINES
      ? { violated: false }
      : { violated: true, message: `staged diff adds ${added} lines (cap: ${MAX_ADDED_LINES})` };
  },
  function checkForbiddenExtensions(_diffText, stagedFiles) {
    const bad = stagedFiles.filter((f) => FORBIDDEN_EXTENSIONS.some((ext) => f.endsWith(ext)));
    return bad.length === 0
      ? { violated: false }
      : { violated: true, message: `forbidden file extensions staged: ${bad.join(", ")}` };
  },
];

// ---- Hook implementation ---------------------------------------------------

function runGuardrail() {
  if (process.env[BYPASS_ENV_VAR] === BYPASS_VALUE) {
    return { allow: true, note: "guardrail bypassed via env var" };
  }
  let diffText = "";
  let stagedFiles = [];
  try {
    diffText = execSync("git diff --staged", { encoding: "utf8" });
    stagedFiles = execSync("git diff --staged --name-only", { encoding: "utf8" })
      .split("\n").map((s) => s.trim()).filter(Boolean);
  } catch (e) {
    return { allow: false, reason: `unable to read staged diff: ${e.message}` };
  }
  const violations = RULES.map((r) => r(diffText, stagedFiles)).filter((r) => r.violated);
  if (violations.length === 0) return { allow: true };
  return {
    allow: false,
    reason: "pre-commit guardrail blocked this commit:\n  - " + violations.map((v) => v.message).join("\n  - "),
  };
}

// ---- Plugin export ---------------------------------------------------------

module.exports = {
  name: "pre-commit-guardrail",
  hooks: {
    "before:git-commit": (ctx) => {
      const result = runGuardrail();
      if (!result.allow) {
        ctx.abort(result.reason);
      }
    },
  },
};
