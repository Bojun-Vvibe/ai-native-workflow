#!/usr/bin/env elvish
# good/02_in_comment.elv — eval mentioned only inside comments.
# example: do not write `eval $code` in production
# also avoid: eval (slurp < $path)
# nor:        eval "echo "$header
echo ok
