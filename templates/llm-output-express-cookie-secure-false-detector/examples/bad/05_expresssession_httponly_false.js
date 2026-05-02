// expressSession alias with httpOnly:false set on cookie block.
const expressSession = require('express-session')
const RedisStore = require('connect-redis').default

module.exports = function buildSession(client) {
  return expressSession({
    store: new RedisStore({ client }),
    secret: process.env.SECRET,
    resave: false,
    saveUninitialized: false,
    cookie: {
      secure: true,
      httpOnly: false,
      sameSite: 'lax',
    },
  })
}
