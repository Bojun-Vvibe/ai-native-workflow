storage "raft" {
  path    = "/vault/data"
  node_id = "node-1"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_cert_file = "/etc/vault/tls/tls.crt"
  tls_key_file  = "/etc/vault/tls/tls.key"
}

api_addr = "https://vault.example.com:8200"
cluster_addr = "https://vault.example.com:8201"
ui = true
