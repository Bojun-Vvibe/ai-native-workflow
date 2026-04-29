#!/usr/bin/env nu
# bad/07_source_after_pipe.nu — source after a pipe; still command pos.
let _ = (echo hi); source $env.MY_INIT
