#!/bin/sh
# Production env file.
export MM_SERVICESETTINGS_SITEURL="https://chat.example.com"
export MM_SERVICESETTINGS_LISTENADDRESS=":8065"
export MM_SERVICESETTINGS_ENABLEDEVELOPER=false
export MM_SERVICESETTINGS_ENABLETESTING=false
exec /opt/mattermost/bin/mattermost server
