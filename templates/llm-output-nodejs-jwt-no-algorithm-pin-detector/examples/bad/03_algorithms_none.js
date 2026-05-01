const jwt = require('jsonwebtoken');

function authenticate(token, key) {
  // BAD: explicitly allowing alg=none. Token signature is not checked.
  return jwt.verify(token, key, { algorithms: ['none'] });
}

module.exports = { authenticate };
