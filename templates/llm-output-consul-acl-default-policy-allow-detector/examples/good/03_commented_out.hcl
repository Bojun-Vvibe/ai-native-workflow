datacenter = "dc1"
data_dir = "/opt/consul"

# Bootstrap migration step (DO NOT ship to prod):
#   acl {
#     default_policy = "allow"
#   }
# Steady-state config below:

acl {
  enabled        = true
  default_policy = "deny"
}
