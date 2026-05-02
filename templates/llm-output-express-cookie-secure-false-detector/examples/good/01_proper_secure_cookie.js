// Properly configured production session.
const express = require('express')
const session = require('express-session')

const app = express()
app.set('trust proxy', 1)

app.use(session({
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: true,
    httpOnly: true,
    sameSite: 'lax',
    maxAge: 1000 * 60 * 60,
  },
}))

module.exports = app
