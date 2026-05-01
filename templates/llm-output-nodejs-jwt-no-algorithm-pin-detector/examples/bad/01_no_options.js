const jwt = require('jsonwebtoken');

function authenticate(token, secret) {
  // BAD: no algorithms allowlist; alg-confusion attack possible.
  const payload = jwt.verify(token, secret);
  return payload;
}

module.exports = { authenticate };
