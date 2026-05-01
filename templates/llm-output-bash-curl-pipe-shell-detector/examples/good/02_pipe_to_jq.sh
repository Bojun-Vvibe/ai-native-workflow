#!/usr/bin/env bash
# Pipe into jq, not into a shell.
curl -fsSL https://api.example.com/v1/things | jq '.[].name'
