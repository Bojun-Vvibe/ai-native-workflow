#!/bin/sh
set -eu
echo "signup_enabled=true" >> /etc/gitlab/gitlab.env
gitlab-ctl reconfigure
