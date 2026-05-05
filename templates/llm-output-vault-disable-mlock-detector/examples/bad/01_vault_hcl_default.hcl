# vault.hcl -- copied from a quickstart blog. Operator silenced the
# dev-mode mlock warning by flipping the toggle.

ui            = true
disable_mlock = true

storage "raft" {
  path    = "/vault/data"
  node_id = "vault-0"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = false
  tls_cert_file = "/vault/tls/tls.crt"
  tls_key_file  = "/vault/tls/tls.key"
}
