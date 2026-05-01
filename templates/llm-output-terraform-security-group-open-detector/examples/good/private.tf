# Good: SSH restricted to a private CIDR. No 0.0.0.0/0, no finding.
resource "aws_security_group" "bastion_safe" {
  name   = "bastion-safe"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8", "172.16.0.0/12"]
  }
}

# Good: public web tier on 443. Port 443 is not in the sensitive set,
# so even 0.0.0.0/0 is allowed by this detector.
resource "aws_security_group" "web" {
  name   = "web-tier"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
