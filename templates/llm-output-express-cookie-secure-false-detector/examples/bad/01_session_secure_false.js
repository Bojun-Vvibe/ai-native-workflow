// Express session with secure: false — classic LLM autocomplete.
const express = require('express')
const session = require('express-session')

const app = express()

app.use(session({
  secret: 'keyboard cat',
  resave: false,
  saveUninitialized: true,
  cookie: { secure: false }
}))

app.get('/', (req, res) => res.send('hi'))
app.listen(3000)
