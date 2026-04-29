#!/usr/bin/env nu
# bad/03_source_interp.nu — interpolated path into source. The
# resolved path depends on $base at runtime.
let base = "/opt/site"
source $"($base)/init.nu"
