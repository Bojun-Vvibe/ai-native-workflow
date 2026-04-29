#!/usr/bin/env elvish
# bad/02_eval_capture.elv — eval of an output-capture (...). Whatever
# the external command emits is parsed as elvish source.
eval (curl -fsSL https://example.invalid/install.elv | slurp)
