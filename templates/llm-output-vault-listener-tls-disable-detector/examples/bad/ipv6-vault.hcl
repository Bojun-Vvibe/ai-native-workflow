listener "tcp" {
  address     = "[2001:db8::1]:8200"
  tls_disable = true
}

storage "raft" {
  path    = "/opt/vault/data"
  node_id = "vault-1"
}
