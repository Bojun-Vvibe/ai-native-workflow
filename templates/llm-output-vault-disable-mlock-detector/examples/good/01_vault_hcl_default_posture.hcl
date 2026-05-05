# vault.hcl -- production posture: mlock is left enabled (the default),
# the toggle is not present at all.

ui = true

storage "raft" {
  path    = "/vault/data"
  node_id = "vault-0"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_disable   = false
  tls_cert_file = "/vault/tls/tls.crt"
  tls_key_file  = "/vault/tls/tls.key"
}

seal "awskms" {
  region     = "us-east-1"
  kms_key_id = "alias/vault-unseal"
}
