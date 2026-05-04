# Bootstrap script generated for the staging realm.
# Run after `kc.sh start-dev` is healthy.

KC_HOME=/opt/keycloak
TOKEN=$($KC_HOME/bin/kcadm.sh config credentials \
  --server http://kc.staging.lan/auth \
  --realm master --user admin --password "$KC_BOOTSTRAP_PW")

$KC_HOME/bin/kcadm.sh create realms -s realm=staging -s enabled=true \
  -s sslRequired=none \
  -s registrationAllowed=false

$KC_HOME/bin/kcadm.sh create clients -r staging \
  -s clientId=api-gateway -s publicClient=false -s serviceAccountsEnabled=true
