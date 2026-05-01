# Bad: standalone aws_security_group_rule for RDP open to the world.
resource "aws_security_group_rule" "rdp_world" {
  type              = "ingress"
  from_port         = 3389
  to_port           = 3389
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.win.id
}

# Bad: full-port open (effectively public to everything).
resource "aws_security_group_rule" "all_ports" {
  type              = "ingress"
  from_port         = 0
  to_port           = 65535
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.win.id
}
