# Documentation snippet warning AGAINST insecure memcached defaults.
# The following is what NOT to do:
#   -l 0.0.0.0
#   -U 11211
# Always pin memcached to localhost or enable -S (SASL).
