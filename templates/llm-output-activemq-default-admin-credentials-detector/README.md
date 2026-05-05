# llm-output-activemq-default-admin-credentials-detector

Detect Apache ActiveMQ ("Classic") configuration that ships the broker with
the well-known default credentials. When asked "give me a working ActiveMQ
config" or "how do I enable the web console", LLMs frequently regenerate the
stock `conf/jetty-realm.properties` (`admin: admin, admin`) or
`conf/credentials.properties` (`activemq.username=system` /
`activemq.password=manager`) verbatim. Anything pointing at the broker's web
console (8161), JMX, OpenWire (61616), or STOMP endpoint can then log in
with `admin/admin` and create/delete queues, drain messages, or change ACLs.

## What bad LLM output looks like

`conf/jetty-realm.properties` shipped from the upstream tarball:

```
admin: admin, admin
user: user, user
```

`conf/credentials.properties` keeping the historical defaults:

```
activemq.username=system
activemq.password=manager
```

`conf/activemq.xml` wiring `<simpleAuthenticationPlugin>` with `admin/admin`:

```xml
<simpleAuthenticationPlugin>
  <users>
    <authenticationUser username="admin" password="admin" groups="admins,users"/>
  </users>
</simpleAuthenticationPlugin>
```

A docker env-file leaving the image defaults intact:

```
ACTIVEMQ_ADMIN_LOGIN=admin
ACTIVEMQ_ADMIN_PASSWORD=admin
```

## What good LLM output looks like

- `jetty-realm.properties` referencing a templated secret
  (`ops: ${OPS_CONSOLE_PASSWORD}, admin`) and no literal `admin: admin`.
- `credentials.properties` with `${VAULT_AMQ_USER}` / `${VAULT_AMQ_PASSWORD}`.
- `activemq.xml` using `<jaasAuthenticationPlugin>` plus
  `<authorizationPlugin>` rather than the simple plugin with hard-coded
  credentials.
- Container env vars renamed (`ACTIVEMQ_ADMIN_LOGIN=ops_console`) and the
  password sourced from the orchestrator's secret store.

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/activemq_simple_auth_admin.xml
BAD  samples/bad/credentials_system_manager.properties
BAD  samples/bad/docker_env_admin_admin.dotenv-example.txt
BAD  samples/bad/jetty_realm_default.properties
GOOD samples/good/activemq_jaas_plugin.xml
GOOD samples/good/credentials_templated.properties
GOOD samples/good/docker_env_secret_ref.dotenv-example.txt
GOOD samples/good/jetty_realm_templated.properties
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good
samples are flagged.

## Detector rules

1. A line of the form `admin[:=]admin` (with optional trailing role list) in
   any `*.properties` realm file — covers the stock
   `conf/jetty-realm.properties` and `conf/users.properties`.
2. `activemq.password=` set to one of the historically-shipped weak values
   (`manager`, `password`, `admin`, `secret`, `changeme`).
3. An `<authenticationUser>` element whose `username="admin"` and
   `password="admin"` (attribute order independent), inside the
   `simpleAuthenticationPlugin`.
4. A docker-compose / env file that sets BOTH `ACTIVEMQ_ADMIN_LOGIN=admin`
   and `ACTIVEMQ_ADMIN_PASSWORD=admin` in the same file.

Comments (`#…` and `<!-- … -->`) are stripped before matching so a commented
example does not trip the detector.
