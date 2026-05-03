datacenter = "dc1"
data_dir   = "/opt/nomad/data"

acl {
  enabled        = true
  token_ttl      = "30s"
  policy_ttl     = "60s"
  role_ttl       = "60s"
}

server {
  enabled          = true
  bootstrap_expect = 3
}
