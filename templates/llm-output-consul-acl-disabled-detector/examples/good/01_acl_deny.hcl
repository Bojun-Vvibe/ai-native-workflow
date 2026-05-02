datacenter = "dc1"
data_dir   = "/opt/consul"

acl {
  enabled        = true
  default_policy = "deny"
  down_policy    = "extend-cache"
  tokens {
    initial_management = "REPLACED-AT-DEPLOY-TIME"
  }
}
