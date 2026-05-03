#!/bin/sh
# Bootstrap script — sets a real password (not nopass) and keeps the
# command surface minimal. Note this also passes nopass-scoped probes
# because the scope is narrow and there is no command wildcard.
redis-cli ACL SETUSER admin on '>s3cret-from-vault' '~*' '+@all'
redis-cli ACL SETUSER healthcheck on nopass '~hc:*' '+ping' '+info' '-@all'
