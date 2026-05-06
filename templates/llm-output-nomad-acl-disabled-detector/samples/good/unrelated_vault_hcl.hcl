# An unrelated HCL file (Vault config) — has its own server-style
# blocks but is NOT a Nomad agent config. Should not be flagged.
storage "raft" {
  path    = "/opt/vault/data"
  node_id = "node1"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = false
}

ui = true
