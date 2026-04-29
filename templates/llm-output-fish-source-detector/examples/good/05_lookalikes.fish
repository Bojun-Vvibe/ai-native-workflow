#!/usr/bin/env fish
# good/05_lookalikes.fish — words that contain "source" as a
# substring or use it as a NON-command. Should not match.
set -l mysource /tmp/x
echo "Reading from datasource $mysource"
function get_source
    echo $mysource
end
# `command source` is still a source call, but with a literal arg:
command source /etc/fish/safe.fish
