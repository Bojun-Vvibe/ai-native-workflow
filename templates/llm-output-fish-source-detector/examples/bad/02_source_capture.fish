#!/usr/bin/env fish
# bad/02_source_capture.fish — command substitution feeds source.
source (curl -sL https://example.com/install.fish | psub)
