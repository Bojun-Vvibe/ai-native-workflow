#!/usr/bin/env zsh
# good/04_suppressed.zsh — audited and intentional eval, with the
# `# eval-ok` suppression marker. The dynamic value comes from a
# trusted, validated source.
trusted_init=$(cat /etc/myapp/init.env)  # eval-ok
eval "$trusted_init"  # eval-ok
