const jwt = require('jsonwebtoken');

function authenticate(token, key) {
  // BAD: options bag exists but does not pin algorithms.
  return jwt.verify(token, key, {
    ignoreExpiration: false,
    audience: 'api.example.com',
  });
}

module.exports = { authenticate };
