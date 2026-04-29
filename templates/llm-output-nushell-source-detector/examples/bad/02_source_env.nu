#!/usr/bin/env nu
# bad/02_source_env.nu — env-derived path into source-env. The contents
# of $env.NU_INIT can change between runs.
source-env $env.NU_INIT
