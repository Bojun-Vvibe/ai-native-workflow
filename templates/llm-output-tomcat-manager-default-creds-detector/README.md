# llm-output-tomcat-manager-default-creds-detector

## Problem

Apache Tomcat's Manager and Host-Manager web applications expose
remote deployment endpoints (`/manager/html`, `/manager/text/deploy`,
`/manager/jmxproxy`, `/host-manager/html`). Any account holding a
role whose name begins with `manager-` or `admin-` can upload a
WAR — i.e. immediate remote code execution.

The stock distribution ships `conf/tomcat-users.xml` with **all
example user entries commented out**. LLM-generated bootstrap
scripts and Dockerfiles routinely reintroduce the example block
verbatim, pairing a privileged role with `tomcat`/`tomcat`,
`admin`/`admin`, `admin`/`password`, or an empty password. Anyone
who can route to port 8080 then owns the host.

## What the insecure pattern looks like

```xml
<tomcat-users>
  <role rolename="manager-gui"/>
  <user username="tomcat" password="tomcat" roles="manager-gui"/>
  <user username="admin"  password=""       roles="manager-gui,admin-gui"/>
</tomcat-users>
```

Variations the detector also catches:

  * `password="s3cret"`, `password="changeit"`, `password="password"`
  * Any role token starting with `manager` or `admin`
  * Username equal to password (e.g. `admin`/`admin`)

## What a safe configuration looks like

  * Manager users defined out-of-band (e.g. CredentialHandler with a
    salted hash, LDAPRealm, JNDIRealm, or short-lived JWT).
  * If `tomcat-users.xml` is used at all, every privileged user has
    a strong, non-default password not equal to the username.
  * Or no privileged user is defined in `tomcat-users.xml` at all.

## How the detector works

`detector.py` strips XML/HTML comments (so the upstream commented
example does not trip it), extracts every active `<user .../>`
element, and emits a finding when:

  * any token in `roles=` begins with `manager` or `admin`, **and**
  * `password=` is in the well-known weak set, is empty, or equals
    `username=`.

Files containing the comment marker
`tomcat-manager-default-creds-allowed` are skipped (useful for
honeypot / CTF fixtures kept on disk).

The script's exit code equals the number of findings.

## Run it

```sh
python3 detector.py path/to/tomcat-users.xml
```

End-to-end self-check:

```sh
bash verify.sh
```

The verifier prints one line of the form
`bad=N/N good=0/N` followed by `PASS` or `FAIL`.
