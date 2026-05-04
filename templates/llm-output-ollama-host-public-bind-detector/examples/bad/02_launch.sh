#!/usr/bin/env bash
# typical homelab launcher copy-pasted from a blog post
set -e
export OLLAMA_HOST=0.0.0.0
exec ollama serve
