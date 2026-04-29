#!/bin/bash
# BAD: GNU sed s///e flag — replacement is executed as a shell command.
# If $USER_INPUT contains shell metacharacters, this is RCE.

USER_INPUT="$1"

# Classic injection: capture group flows into shell exec.
echo "host=$USER_INPUT" | sed 's/host=\(.*\)/echo \1/e'

# Same idea, alternate delimiter, with extra flags around the e.
echo "$USER_INPUT" | sed 's|^|date +%s; |gie'

# Another delimiter still flagged.
sed -e 's#FOO#whoami#e' input.txt

# Standalone GNU `e COMMAND` — executes the literal command and inserts
# its stdout. Still a sink whenever COMMAND is templated.
sed -i -e '/MARKER/e cat /etc/passwd' notes.txt

# Address + e command, also flagged.
echo bar | sed '2e uname -a'
