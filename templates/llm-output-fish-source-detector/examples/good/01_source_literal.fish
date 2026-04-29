#!/usr/bin/env fish
# good/01_source_literal.fish — fully literal path. No $, no (.
# Constant path = no injection surface; detector skips it.
source ~/.config/fish/aliases.fish
source /etc/fish/conf.d/site.fish
echo done
