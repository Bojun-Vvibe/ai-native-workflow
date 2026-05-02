#!/usr/bin/env bash
# run-tests.sh — worked example runner for llm-output-harbor-default-admin-password-detector
# Runs detect.sh against every fixture in samples/ and prints PASS/FAIL plus
# the bad=X/Y good=X/Y tally line.
set -u
cd "$(dirname "$0")"
bash detect.sh samples/bad-*.txt samples/good-*.txt
