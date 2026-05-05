#!/bin/bash
# Bring up the test rig.
mmctl --local config set ServiceSettings.EnableTesting true
mattermost server -ServiceSettings.EnableDeveloper=true --config /etc/mattermost/config.json
