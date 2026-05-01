# A README that mentions vault server -dev inside a comment must NOT
# trigger the detector. We commonly document what we DO NOT do.
#
# Do NOT run: vault server -dev
# Do NOT set: VAULT_DEV_ROOT_TOKEN_ID=root
#
# Production uses a Raft storage backend with auto-unseal via KMS.
storage = "raft"
