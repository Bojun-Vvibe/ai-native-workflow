// Behind a TLS-terminating proxy: secure: 'auto' is honored when
// trust proxy is set, so the cookie is sent only over HTTPS in
// production.
import express from 'express'
import session from 'express-session'

const app = express()
app.set('trust proxy', 1)

app.use(session({
  secret: process.env.SESSION_SECRET ?? 'change-me',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: 'auto',
    httpOnly: true,
    sameSite: 'lax',
  },
}))

export default app
