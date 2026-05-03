#!/usr/bin/env bash
# Quickstart: start rethinkdb with the admin password "explicitly empty"
# so the bootstrap script can run without any password prompt.
exec rethinkdb --bind all --initial-password ""
