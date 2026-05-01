const jwt = require('jsonwebtoken');

function authenticate(token, secret) {
  // GOOD: pinned to HS256 only.
  return jwt.verify(token, secret, { algorithms: ['HS256'] });
}

module.exports = { authenticate };
