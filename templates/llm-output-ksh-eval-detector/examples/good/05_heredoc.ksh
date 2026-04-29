#!/bin/ksh
# Heredoc body that contains the literal string `eval` must not
# flag, because the body is data passed to another command, not
# shell input re-parsed by this shell.
cat <<DOC
  example: eval "$x"
  example: source ./helper.ksh
  example: ${!varname}
DOC
print "done"
