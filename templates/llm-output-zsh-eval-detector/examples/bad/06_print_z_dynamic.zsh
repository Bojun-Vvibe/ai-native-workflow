#!/usr/bin/env zsh
# bad/06_print_z_dynamic.zsh — print -z pushes onto the line editor
# buffer; equivalent to eval once the user hits return. Dynamic form
# is dangerous in interactive widgets.
suggested="rm -rf $TARGET"
print -z $suggested
