# An unrelated nested block that happens to use the same key name.
# This is not Consul ACL config -- it's a hypothetical sibling
# subsystem block, and must not produce a finding.

intentions {
  default_policy = "allow"
}

acl {
  enabled        = true
  default_policy = "deny"
}
