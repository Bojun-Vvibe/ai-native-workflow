# Nomad config — acl block but explicitly disabled.
datacenter = "dc1"
data_dir   = "/opt/nomad/data"

server {
  enabled          = true
  bootstrap_expect = 1
}

acl {
  enabled = false
}
