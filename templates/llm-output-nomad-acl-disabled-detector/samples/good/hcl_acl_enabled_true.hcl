# Nomad server with ACLs properly enabled.
datacenter = "dc1"
data_dir   = "/opt/nomad/data"

server {
  enabled          = true
  bootstrap_expect = 3
}

client {
  enabled = true
}

acl {
  enabled                  = true
  token_ttl                = "30s"
  policy_ttl               = "60s"
  replication_token        = "REDACTED"
}
