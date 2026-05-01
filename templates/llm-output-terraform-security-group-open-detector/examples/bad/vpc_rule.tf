# Bad: new-style aws_vpc_security_group_ingress_rule with cidr_ipv4 string.
resource "aws_vpc_security_group_ingress_rule" "k8s_api" {
  security_group_id = aws_security_group.cluster.id

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "tcp"
  from_port   = 6443
  to_port     = 6443
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  security_group_id = aws_security_group.cache.id

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "tcp"
  from_port   = 6379
  to_port     = 6379
}
