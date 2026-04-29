#!/usr/bin/env elvish
# good/04_suppressed.elv — audited intentional eval, with the
# `# eval-ok` suppression marker. The dynamic value is a constant
# loaded from a trusted bundled config at build time.
var trusted-init = (slurp < /etc/myapp/init.elv)  # eval-ok
eval $trusted-init  # eval-ok
