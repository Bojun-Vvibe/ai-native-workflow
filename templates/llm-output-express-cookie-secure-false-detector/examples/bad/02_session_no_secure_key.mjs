// Cookie block present but missing `secure` key entirely — Express
// defaults to false, so this is shipped insecure-by-default.
import express from 'express'
import session from 'express-session'

const app = express()

app.use(
  session({
    secret: process.env.SESSION_SECRET || 'dev-only',
    resave: false,
    saveUninitialized: false,
    cookie: {
      httpOnly: true,
      maxAge: 1000 * 60 * 60 * 24,
    },
  }),
)

export default app
