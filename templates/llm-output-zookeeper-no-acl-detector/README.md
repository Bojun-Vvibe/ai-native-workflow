# llm-output-zookeeper-no-acl-detector

Detect ZooKeeper client snippets and bootstrap scripts that create
znodes with a wide-open ACL — i.e. any client (including anonymous
ones) gets full CREATE+READ+WRITE+DELETE+ADMIN permissions.

This detector is intentionally distinct from
`llm-output-zookeeper-no-auth-detector` (which targets server-side
configuration that disables SASL/Kerberos altogether). ZooKeeper ACLs
are a **per-znode** authorization layer that is orthogonal to
authentication: even a server that *requires* SASL will still honour
`OPEN_ACL_UNSAFE` znodes for unauthenticated clients, because the ACL
on the znode says "anyone is allowed". An attacker who can reach the
ZooKeeper port can therefore read secrets, alter cluster membership,
or wipe znodes — without ever authenticating.

LLMs commonly emit `Ids.OPEN_ACL_UNSAFE` (Java/Scala/Kotlin),
`OPEN_ACL_UNSAFE` (Python `kazoo`), or `setAcl /path world:anyone:cdrwa`
(zkCli) when asked to "seed config in ZooKeeper", because those are the
shortest paths in the official quickstart docs.

## What bad LLM output looks like

Java with `ZooDefs.Ids.OPEN_ACL_UNSAFE`:

```java
zk.create("/app/config", data, Ids.OPEN_ACL_UNSAFE, CreateMode.PERSISTENT);
```

Python `kazoo` with `OPEN_ACL_UNSAFE`:

```python
zk.create("/svc/leader", b"node-1", acl=OPEN_ACL_UNSAFE)
```

Shell with `world:anyone:cdrwa`:

```sh
setAcl /app/db-password world:anyone:cdrwa
```

`world:anyone:r`, `world:anyone:rwa`, etc. (any subset of `cdrwa`) are
all flagged because they grant the listed perms to every connected
client.

## What good LLM output looks like

Java digest ACL bound to an auth principal:

```java
Id digest = new Id("digest", "svc:hashedpw");
ACL acl   = new ACL(Perms.READ | Perms.WRITE, digest);
zk.create("/app/config", data, List.of(acl), CreateMode.PERSISTENT);
```

zkCli digest ACL:

```sh
addauth digest svc:secret
setAcl /app digest:svc:hashedpw:rw
```

A file that does **not** look like ZooKeeper usage is not flagged —
see `samples/good-3.txt`.

## How the detector decides

1. Decide that the file is ZooKeeper-related: it must mention
   `zookeeper`, `kazooclient`, `zkclient`, `zk.create`,
   `curatorframework`, `zkcli`, or `org.apache.zookeeper`. If none of
   those appear, do not flag.
2. On every non-comment line, look for any of:
   - The bareword `OPEN_ACL_UNSAFE` (covers both
     `Ids.OPEN_ACL_UNSAFE` and `from kazoo.security import OPEN_ACL_UNSAFE`),
   - A `world:anyone:<perms>` triple where `<perms>` is any subset of
     `cdrwa`,
   - `ANYONE_ID_UNSAFE` combined with `Perms.ALL` / `0x1f` / `31`
     (the long-form way of building the same wide-open ACL).
3. Trailing `//` and `#` comments are stripped before matching, so
   prose mentions of `OPEN_ACL_UNSAFE` in a comment do not flag.

## Run the worked example

```sh
bash run-tests.sh
```

Expected output:

```
bad=4/4 good=0/4 PASS
```

The four bad fixtures cover: Java `Ids.OPEN_ACL_UNSAFE`, Python
`kazoo` `OPEN_ACL_UNSAFE`, zkCli `world:anyone:cdrwa`, and Kotlin /
Curator `ZooDefs.Ids.OPEN_ACL_UNSAFE`. The four good fixtures cover:
Java digest ACL, kazoo `make_digest_acl`, an unrelated file that
mentions the constant only in a comment, and zkCli with `digest:`
ACL entries.

## Run against your own files

```sh
bash detect.sh path/to/Bootstrap.java path/to/seed.py path/to/zkcli.sh
# or via stdin:
cat seed.py | bash detect.sh
```

Exit code is `0` only if every `bad-*` sample is flagged and no
`good-*` sample is flagged, so this is safe to wire into CI as a
defensive misconfiguration gate for ZooKeeper deployments.
