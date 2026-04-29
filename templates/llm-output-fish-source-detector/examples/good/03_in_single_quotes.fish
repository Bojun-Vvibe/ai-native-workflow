#!/usr/bin/env fish
# good/03_in_single_quotes.fish — fish single quotes do NOT
# interpolate. The `$x` inside is literal text, not an expansion.
echo 'source $x is just a string'
echo 'source (whoami) too'
