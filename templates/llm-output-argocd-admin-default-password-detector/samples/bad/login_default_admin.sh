#!/usr/bin/env bash
# bootstrap a fresh argo cd install
kubectl port-forward svc/argocd-server -n argocd 8080:443 &
sleep 2
argocd login localhost:8080 --username admin --password admin --insecure
argocd app create my-app --repo https://example.com/repo.git --path . --dest-server https://kubernetes.default.svc --dest-namespace default
