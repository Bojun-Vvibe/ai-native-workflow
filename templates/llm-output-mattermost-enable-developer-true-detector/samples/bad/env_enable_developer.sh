#!/bin/sh
# Compose env file shipped with the deployment.
export MM_SERVICESETTINGS_SITEURL="https://chat.example.com"
export MM_SERVICESETTINGS_LISTENADDRESS=":8065"
export MM_SERVICESETTINGS_ENABLEDEVELOPER=true
export MM_SERVICESETTINGS_ENABLELOCALMODE=false
exec /opt/mattermost/bin/mattermost server
