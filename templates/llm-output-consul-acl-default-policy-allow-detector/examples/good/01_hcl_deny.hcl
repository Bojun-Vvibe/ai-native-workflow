datacenter = "dc1"
data_dir = "/opt/consul"

acl {
  enabled        = true
  default_policy = "deny"
  enable_token_persistence = true
}
