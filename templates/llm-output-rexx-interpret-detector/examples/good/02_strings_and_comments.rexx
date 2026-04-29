/* 02_strings_and_comments.rexx
   Mentions of "interpret cmd" and "call value(x)" inside string
   literals and comments must not flag. */
say "the keyword is interpret cmd, but this is just text"
say 'do not call value(x) here either'
-- doc: we deliberately do not use INTERPRET in this script
exit 0
