# llm-output-express-cookie-secure-false-detector

Detects Express / Koa / Fastify session and cookie configuration where
the session cookie is created without the `secure` flag (or with
`secure: false`) **and** without restricting it to a development-only
code path. Optionally also flags the same call site when `httpOnly` is
explicitly `false`.

## Why this matters

A session cookie issued without `Secure` is sent over plain HTTP. Any
on-path observer (open Wi-Fi, captive portal, transparent proxy) can
copy the cookie and replay it to the origin. With `httpOnly: false` the
cookie is also exposed to any DOM XSS — at which point the session is
trivially exfiltratable to an attacker-controlled URL.

LLM autocompletes for Express session middleware overwhelmingly emit:

    app.use(session({
      secret: 'keyboard cat',
      resave: false,
      saveUninitialized: true,
      cookie: { secure: false }
    }))

because that is the shape that "just works" against `http://localhost`.
The same snippet then ships to production unchanged. The detector is
meant to be run by the LLM caller before that snippet is offered to a
human reviewer.

## What it detects

For each scanned JS / TS file, the detector looks for a `cookie: { … }`
object literal that is the argument of a session-middleware call
(`session(...)`, `cookieSession(...)`, `expressSession(...)`,
`fastifySession.register(...)`, `app.use(session(...))`, …) and reports
a finding when **any** of:

1. `secure` is the literal `false`, AND the surrounding file is not a
   pure test file (path does not contain `/test/`, `__tests__`, or
   `.spec.`/`.test.`).
2. The `cookie` block is present but has no `secure` key at all
   (Express defaults to `false`, so the cookie is insecure by default).
3. `httpOnly: false` is set explicitly on the same cookie block.

A finding is suppressed if the same line or the line immediately above
the `cookie:` block contains the marker `// llm-cookie-insecure-ok`
(escape hatch for genuine localhost-only test fixtures).

## What it does NOT detect

- `res.cookie('name', value, { secure: false })` calls outside a
  session-middleware context. Those are covered by a sibling detector.
- TLS termination at an upstream proxy with `trust proxy` set — the
  detector cannot prove the proxy adds `Secure` itself. Authors who
  rely on that pattern should keep `secure: 'auto'` (which Express
  honors when `trust proxy` is on) and the detector will not flag.
- Cookie configuration loaded from a runtime variable
  (`cookie: cookieOpts`). The detector only reasons about literal
  object syntax that the LLM emitted directly.

## How to fix

```js
app.use(session({
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: true,        // require HTTPS
    httpOnly: true,      // not visible to document.cookie
    sameSite: 'lax',     // CSRF mitigation
    maxAge: 1000 * 60 * 60
  }
}))
```

If the deployment is behind a TLS-terminating proxy:

```js
app.set('trust proxy', 1)
app.use(session({ /* ... */, cookie: { secure: 'auto', httpOnly: true } }))
```

## Usage

```
python3 detector.py path/to/app.js
python3 detector.py path/to/src/
bash verify.sh
```

Exit code is the number of files with at least one finding (capped at
255). Stdout lines have the form `<file>:<line>:<reason>`.
