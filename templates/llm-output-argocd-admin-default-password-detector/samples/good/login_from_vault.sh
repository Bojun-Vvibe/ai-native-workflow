#!/usr/bin/env bash
# log in using the rotated password pulled from a secret manager
ARGO_PW="$(vault kv get -field=password secret/argocd/admin)"
argocd login argocd.example.com --username admin --password "$ARGO_PW" --grpc-web
unset ARGO_PW
