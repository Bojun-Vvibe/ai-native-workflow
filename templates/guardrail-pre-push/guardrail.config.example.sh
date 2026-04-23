# Example guardrail config.
# Copy to ~/.config/guardrail/guardrail.config.sh and edit.
# DO NOT commit your real config to a public repo — the whole point of
# the internal-pattern blacklist is that the patterns themselves are
# sensitive.

# ----- Scope: only enforce when pushing to a remote URL containing this -----
SCOPE_FILTER="github.com/your-account/"

# ----- Block 1: internal-string blacklist -----
# Patterns are POSIX extended regex, joined by | inside one big group.
# Add your employer codenames, internal repo names, internal hostnames,
# project codenames, NDA-covered terms.
INTERNAL_PATTERNS='(your-employer-domain\.com|internal-codename-1|internal-codename-2|internal-host\.example\.net)'

# ----- Block 2: secret patterns (defaults are usually fine) -----
# Override only to add provider-specific keys not covered by defaults.
# SECRET_PATTERNS='...'

# ----- Block 3: forbidden filenames (defaults usually fine) -----
# Override to add company-specific config files you must never push.
# FORBIDDEN_FILES='...'

# ----- Block 4: max blob size in bytes -----
MAX_BLOB_BYTES=5242880   # 5 MB

# ----- Block 5: offensive-security artifact fingerprints -----
ENABLE_BLOCK_5_ATTACK_PATTERNS=1
# ATTACK_PATTERNS='...'  # override if you legitimately work on red-team tooling

# ----- Bounded scan -----
MAX_COMMITS_SCANNED=500
MAX_COMMITS_NEW_BRANCH=200
