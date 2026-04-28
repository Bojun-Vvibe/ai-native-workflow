#!/usr/bin/env bash
# Bad fixture: 5+ instances of `eval STRING` that should each be flagged.

set -euo pipefail

cmd="ls -la"
eval "$cmd"                                # 1: variable into eval

action=$1
eval $action                                # 2: unquoted variable into eval

result=$(eval "$(cat /tmp/payload.sh)")     # 3: command substitution into eval
echo "$result"

run_for() {
    local target=$1
    eval "deploy_$target --force"           # 4: interpolated string
}
run_for prod

# Even literal-looking strings get flagged — the smell is `eval` itself:
eval 'echo hello world'                     # 5: literal-string eval

# Inside a conditional / pipeline / brace block — still detected:
if [ -n "$cmd" ]; then eval "$cmd"; fi      # 6: after `then`
true && eval "$cmd"                         # 7: after &&
{ eval "$cmd"; }                            # 8: inside brace group
