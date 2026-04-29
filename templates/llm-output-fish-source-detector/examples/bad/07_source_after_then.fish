#!/usr/bin/env fish
# bad/07_source_after_then.fish — `then` keyword can precede a command;
# argument is a variable.
if test -f $userfile
    source $userfile
end
