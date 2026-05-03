ui = true
disable_mlock = false

storage "raft" {
  path    = "/vault/data"
  node_id = "node-1"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/vault/tls/tls.crt"
  tls_key_file  = "/vault/tls/tls.key"
}
