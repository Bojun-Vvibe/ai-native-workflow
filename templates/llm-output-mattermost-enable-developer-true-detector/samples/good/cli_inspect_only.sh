#!/bin/bash
# Read-only inspection — no mutation.
mmctl --local config get ServiceSettings.EnableDeveloper
mmctl --local config get ServiceSettings.EnableTesting
mattermost version
