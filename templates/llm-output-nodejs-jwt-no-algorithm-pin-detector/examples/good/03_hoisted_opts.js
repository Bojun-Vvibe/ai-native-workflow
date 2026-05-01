const jwt = require('jsonwebtoken');

const verifyOpts = {
  algorithms: ['HS256'],
  audience: 'api.example.com',
};

function authenticate(token, secret) {
  // GOOD: hoisted opts pin algorithms.
  return jwt.verify(token, secret, verifyOpts);
}

module.exports = { authenticate };
