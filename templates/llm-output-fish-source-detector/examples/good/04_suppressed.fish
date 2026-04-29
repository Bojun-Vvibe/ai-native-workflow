#!/usr/bin/env fish
# good/04_suppressed.fish — auditor reviewed and pinned this; the
# trailing # source-ok marker silences the finding.
set -l p /opt/vendor/init.fish
source $p  # source-ok — vendor-controlled path on read-only volume
