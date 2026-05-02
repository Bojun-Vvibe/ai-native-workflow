# llm-output-zookeeper-no-auth-detector

Detect Apache ZooKeeper configurations and `zkCli.sh` snippets that disable
authentication entirely. LLMs love to suggest the "easy" path
(`skipACL=yes`, `world:anyone:cdrwa`, no `authProvider.*`) when asked how to
"get ZooKeeper running quickly", which leaves coordination data — service
discovery entries, leader election state, sometimes secrets — open to anyone
who can reach the client port.

## What bad LLM output looks like

`zoo.cfg` with ACLs globally disabled:

```
clientPort=2181
skipACL=yes
```

A reachable `zoo.cfg` with no auth provider at all:

```
clientPort=2181
4lw.commands.whitelist=*
# no authProvider.* line, no requireClientAuthScheme
```

A `zkCli.sh` transcript that grants the world full rights:

```
setAcl /app world:anyone:cdrwa
```

## What good LLM output looks like

SASL required for every client:

```
authProvider.1=org.apache.zookeeper.server.auth.SASLAuthenticationProvider
requireClientAuthScheme=sasl
```

Or scoped to loopback only:

```
clientPortAddress=127.0.0.1
```

Or a digest-scheme ACL with a real principal:

```
addauth digest deployer:<from-secret-store>
setAcl /app digest:deployer:<base64-sha1>:cdrwa
```

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/no_auth_provider.conf
BAD  samples/bad/skipacl_yes.conf
BAD  samples/bad/world_anyone_cdrwa.sh
GOOD samples/good/digest_acl.sh
GOOD samples/good/loopback_only.conf
GOOD samples/good/sasl_required.conf
bad=3/3 good=0/3 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good samples
are flagged.

## Detector rules

1. `skipACL=yes` anywhere in the file.
2. Any `world:anyone:` ACL that grants admin (`a`) — covers the common
   `cdrwa` shorthand.
3. `4lw.commands.whitelist=*` (admin 4-letter words exposed) without any
   `authProvider.*=` line.
4. `clientPort=` set, no `authProvider.*`, no `requireClientAuthScheme=`,
   and not pinned to a loopback `clientPortAddress`.
