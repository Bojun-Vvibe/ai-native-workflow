# llm-output-nodejs-https-reject-unauthorized-false-detector

Pure-stdlib node single-pass scanner that flags **disabled TLS
certificate verification** in Node.js source. Catches the classic
"just make the cert error go away" footgun where an LLM-suggested
fix silently downgrades every outbound HTTPS request from
`example.test`-pinned-CA to "trust whatever you get", letting any
on-path attacker MITM the traffic.

## What it catches

Three concrete shapes:

- **`rejectUnauthorized: false`** (or `0`) anywhere in an object
  literal — `https.Agent`, `tls.connect`, `https.request`,
  `axios.create({ httpsAgent })`, `node-fetch` agent, etc.
- **`process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'`** (or `"0"`,
  or numeric `0`) — the global nuclear option that disables
  verification for every later HTTPS / TLS call in the process,
  including dependencies you don't control.
- **`https.globalAgent.options.rejectUnauthorized = false`** —
  same global blast radius, different ergonomic.

Finding kinds:

- `tls-rejectunauthorized-false`
- `tls-env-disable`
- `tls-globalagent-disable`

Lines marked with a trailing `// tls-noverify-ok` comment are
suppressed. Occurrences inside `// ...` line comments,
`/* ... */` block comments, and `'`/`"`/`` ` `` string literals
are ignored.

## Files

- `detect.js` — single-file node stdlib scanner (no deps).
- `examples/bad/` — six `.js` files exercising all three flagged
  surfaces (axios httpsAgent, env-var nuke, global agent poke,
  node-fetch, tls.connect, numeric-zero variants).
- `examples/good/` — four `.js` files showing the safe shapes
  (`rejectUnauthorized: true` with pinned CA, prose-only
  mentions, audited-and-suppressed test fixture, similarly-named
  identifiers that must not match).
- `verify.sh` — runs the detector against `bad/` and `good/`
  and asserts the expected counts and exit codes.

## Run

```bash
bash verify.sh
```

Expected: `PASS`, with at least 6 findings against `bad/` and 0
against `good/`.

## Safe replacement patterns

```js
// The only safe shape — verify the chain, optionally pin a CA.
const https = require('https');
const agent = new https.Agent({
  rejectUnauthorized: true,
  ca: fs.readFileSync('ca.pem'),
});

// If the upstream is genuinely self-signed, pin its cert /
// fingerprint instead of disabling verification. Never blanket-
// disable in production.
```

If a test fixture really must talk to a self-signed local
service, pin the CA and add an audit comment on the line:

```js
rejectUnauthorized: false, // tls-noverify-ok — fixtures only
```

## Why LLMs emit the bad shape

`UNABLE_TO_VERIFY_LEAF_SIGNATURE` is one of the most common
Node.js stack traces on Stack Overflow, and the top-voted "fix"
for the entire decade was `rejectUnauthorized: false`. The unsafe
shape is one-line, requires no key material, and makes the error
disappear immediately — so it dominates the training corpus.
