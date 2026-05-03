#!/usr/bin/env bash
# Bad: helm install of kong-gateway disables RBAC explicitly.
helm install my-kong kong/kong --set enterprise.rbac.enabled=false
