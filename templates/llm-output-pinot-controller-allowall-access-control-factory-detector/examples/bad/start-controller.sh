#!/usr/bin/env bash
# start apache pinot controller
set -eu
PINOT_HOME=/opt/pinot
exec java -Xms2g -Xmx4g \
  -Dcontroller.admin.access.control.factory.class=org.apache.pinot.controller.api.access.AllowAllAccessControlFactory \
  -Dlog4j2.configurationFile="${PINOT_HOME}/conf/log4j2.xml" \
  -cp "${PINOT_HOME}/lib/*" \
  org.apache.pinot.tools.admin.PinotAdministrator \
  StartController -configFileName "${PINOT_HOME}/conf/controller.conf"
