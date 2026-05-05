# llm-output-puppet-server-autosign-true-detector

Static lint that flags Puppet master/server configurations
(`puppet.conf`) which enable unconditional autosigning of agent
certificates.

When asked "set up a puppet master and let new nodes join", LLMs
routinely paste:

```ini
[master]
autosign = true
```

…or, equivalently, write `/etc/puppetlabs/puppet/autosign.conf`
containing a single wildcard line:

```
*
```

Either form tells the Puppet CA to sign **every** certificate signing
request (CSR) it receives, with no policy executable and no allowlist.
Any host that can reach TCP/8140 can then enroll, pull catalogs (which
typically contain secrets, passwords, SSH keys, and remote-exec
recipes), and report fabricated facts. This is the default
"compromise the entire fleet" misconfig for Puppet.

Safe forms include:

- `autosign = false` (the operator manually signs each CSR, or uses
  an out-of-band CSR-attribute / pre-shared-key flow);
- `autosign = /etc/puppetlabs/puppet/autosign.sh` (a *policy-based*
  autosigner — a path to an executable that decides per CSR);
- An `autosign.conf` allowlist that lists explicit hostnames or
  bounded glob suffixes (`*.nodes.internal.example`) instead of a
  bare `*`.

## Bad patterns this catches

1. `puppet.conf` with `autosign = true` (any case, optionally with
   spaces) under `[master]`, `[server]`, or `[main]`.
2. `puppet.conf` with `autosign = *` (literal asterisk value).
3. An `autosign.conf` file (filename ends in `autosign.conf`) whose
   only non-comment, non-blank line is `*`.

## Good patterns

- `autosign = false`.
- `autosign = /etc/puppetlabs/puppet/autosign.sh` (policy executable).
- `autosign.conf` listing explicit hostnames or bounded suffixes,
  with no bare `*` line.
- Files that mention `autosign = true` only inside a `#` / `;`
  comment.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Exit 0 iff every bad sample is flagged AND no good sample is.
