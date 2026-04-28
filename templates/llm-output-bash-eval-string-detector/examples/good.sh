#!/usr/bin/env bash
# Good fixture: same intents as bad.sh, expressed without `eval`.

set -euo pipefail

# Use arrays instead of `eval` for "variable holds a command":
cmd=(ls -la)
"${cmd[@]}"

# Dispatch by name with a case statement, not eval:
action=${1:-noop}
case "$action" in
    deploy)  ./deploy.sh ;;
    rollback) ./rollback.sh ;;
    noop)    : ;;
    *)       echo "unknown: $action" >&2; exit 1 ;;
esac

# Read external script and run it in a subshell, no eval:
bash /tmp/payload.sh

# Variable interpolation in strings is fine when not fed to eval:
target=prod
echo "deploying to $target"

# Mention of the word eval inside a comment must not trigger:
# (do not use eval here — replaced with case above)

# Mention of "eval" inside a quoted string must not trigger:
echo "the word eval should not be detected inside a quoted string"

# An intentional, audited eval can be suppressed inline:
eval 'echo audited' # eval-ok: build-time only, no user input
