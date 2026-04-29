#!/usr/bin/env elvish
# bad/08_eval_concat.elv — eval of a concatenated string built from
# a literal prefix plus a $var. Common LLM idiom: "build a command".
var name = 'world'
eval 'echo hello '$name
