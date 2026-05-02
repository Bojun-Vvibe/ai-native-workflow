// cookie-session middleware with explicit insecure flags.
const express = require('express')
const cookieSession = require('cookie-session')

const app = express()

app.use(cookieSession({
  name: 'sid',
  keys: ['secret-1', 'secret-2'],
  cookie: {
    secure: false,
    httpOnly: false,
    sameSite: 'none',
    maxAge: 24 * 60 * 60 * 1000,
  },
}))

module.exports = app
