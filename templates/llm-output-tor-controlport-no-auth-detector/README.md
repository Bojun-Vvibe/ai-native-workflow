# llm-output-tor-controlport-no-auth-detector

Detect Tor `torrc` configurations that LLMs commonly emit with a
TCP `ControlPort` open AND no working authentication mechanism.
Tor's control port speaks a text protocol that lets a connected
client reload config, fetch keys, change `SocksPort`, dump
circuits, and issue `SIGNAL NEWNYM` / `GETINFO` / `SETCONF`.
With no auth, any local process — and, if the port binds publicly,
any host on the network — can fully control the relay or client.

When asked "give me a Tor config that exposes the control port for
my Python `stem` script" or "let nyx connect to my Tor", models
routinely:

- Add `ControlPort 9051` and stop there, forgetting that the
  control port has no default auth.
- Add `CookieAuthentication 0` because they read a snippet that
  used hashed-password auth and "simplified" it.
- Bind `ControlPort 0.0.0.0:9051` to "make it reachable from my
  laptop" with cookie auth that is fundamentally local-only.
- Render `HashedControlPassword CHANGEME` (or `TODO`,
  `<your-hash-here>`) and ship the file as-is.

## Bad patterns

1. `ControlPort <num>` (TCP form) with no `HashedControlPassword`
   and no `CookieAuthentication 1`.
2. `ControlPort <num>` with `CookieAuthentication 0` and no
   `HashedControlPassword`.
3. `ControlPort 0.0.0.0:<num>` / `ControlPort *:<num>` /
   `ControlPort [::]:<num>` (public bind) with cookie-only auth —
   cookie auth requires reading the local cookie file, which a
   remote client cannot do, so this is functionally unauthenticated
   from the network's perspective.
4. `HashedControlPassword` set to an empty string or a placeholder
   like `CHANGEME` / `TODO` / `xxx` / `placeholder` / `replaceme`.

## Good patterns

- No `ControlPort` line at all (default: control port disabled).
- `ControlPort` with a real `HashedControlPassword 16:...` value.
- `ControlPort 127.0.0.1:<num>` (or `::1:<num>`) with
  `CookieAuthentication 1`.
- `ControlSocket /var/run/tor/control` (Unix domain socket) used
  in place of a TCP control port; filesystem permissions gate
  access.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-controlport-no-auth.torrc
BAD  samples/bad/02-cookie-auth-zero.torrc
BAD  samples/bad/03-public-bind-cookie-only.torrc
BAD  samples/bad/04-hashed-password-placeholder.torrc
GOOD samples/good/01-no-controlport.torrc
GOOD samples/good/02-hashed-password.torrc
GOOD samples/good/03-loopback-cookie-auth.torrc
GOOD samples/good/04-controlsocket-only.torrc
bad=4/4 good=0/4 PASS
```

## Why this matters

The Tor control protocol is the management plane for a Tor process:
a connected client can read the relay's identity keys, change which
exits the SocksPort uses, install new hidden services, and tell the
process to restart with a different config. An unauthenticated
control port is therefore a remote root-ish handle on the Tor
process — for a relay operator that means deanonymisation of every
circuit, and for a hidden-service operator it means immediate
disclosure of the onion's identity key.

CVE-2014-7826 / GitLab CVE-2017-7591 / repeated GitHub config
audits show this pattern recurs because the syntax is forgiving:
`ControlPort 9051` is a complete, parseable line and Tor will
happily start with it. The detector codifies the four shapes that
LLM output tends to land in.

The detector is deliberately narrow:

- It does not fire on configs that omit `ControlPort` entirely.
- It does not fire on `ControlPort 0` (the explicit-disable spelling).
- It does not fire on `ControlPort unix:/path` (which is just a
  ControlSocket spelled differently).
- It accepts the `tor --hash-password` style `16:...` hashed
  password as valid, but rejects empty / placeholder values.
- It strips `#` line comments so that documentation that quotes
  the bad pattern inside a comment doesn't false-fire.

Bash 3.2+ / awk / coreutils only. No network calls.
