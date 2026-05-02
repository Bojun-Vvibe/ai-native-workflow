// Localhost-only fixture loaded in dev mode.
const session = require('express-session')

module.exports = session({
  secret: 'dev',
  resave: false,
  saveUninitialized: true,
  // llm-cookie-insecure-ok
  cookie: { secure: false, httpOnly: false },
})
