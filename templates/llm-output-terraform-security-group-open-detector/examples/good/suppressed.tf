# Good: per-block suppression with `# sg-open-ok`.
# Triple-reviewed exception — managed admin host with WAF in front.
resource "aws_security_group" "managed_admin" {
  name   = "managed-admin"
  vpc_id = var.vpc_id

  ingress { # sg-open-ok
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Good: file-level interop suppression honoured by tfsec / checkov.
# tfsec:ignore:sg-open
resource "aws_security_group_rule" "legacy_admin" {
  type              = "ingress"
  from_port         = 5432
  to_port           = 5432
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = "sg-deadbeef"
}
