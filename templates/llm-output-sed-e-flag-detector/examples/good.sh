#!/bin/bash
# GOOD: no `e` flag, no standalone `e COMMAND`. Pure textual rewrite.

USER_INPUT="$1"

# Plain substitution, no execution.
echo "host=$USER_INPUT" | sed 's/host=\(.*\)/host is \1/'

# Multiple flags, none of them `e`.
echo "$USER_INPUT" | sed 's|^|prefix: |g'

# Different delimiters, still no `e`.
sed -e 's#FOO#BAR#g' input.txt
sed -e 's,a,b,I' input.txt

# `s/.../.../` followed by an unrelated command on a new line.
sed -e 's/foo/bar/' -e 'd' input.txt

# A documented, intentional execution case is suppressed inline. The
# detector should not flag this line.
sed 's/X/date/e' trusted.txt   # sed-e-ok: input is generator-controlled

# Words containing the letter e in flag-like positions but not actually
# the s///e flag.
echo "users/admin/role/edit" > /tmp/route
grep -E '^/users/' /tmp/route
