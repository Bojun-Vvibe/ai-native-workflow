#!/usr/bin/env bash
# start apache pinot controller
set -eu
PINOT_HOME=/opt/pinot
: "${PINOT_AUTH_FACTORY:?PINOT_AUTH_FACTORY must be set}"
exec java -Xms2g -Xmx4g \
  -Dcontroller.admin.access.control.factory.class="${PINOT_AUTH_FACTORY}" \
  -Dlog4j2.configurationFile="${PINOT_HOME}/conf/log4j2.xml" \
  -cp "${PINOT_HOME}/lib/*" \
  org.apache.pinot.tools.admin.PinotAdministrator \
  StartController -configFileName "${PINOT_HOME}/conf/controller.conf"
