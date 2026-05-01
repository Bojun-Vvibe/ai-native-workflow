const jwt = require('jsonwebtoken');

function authenticate(token, publicKey) {
  // GOOD: multi-algorithm allowlist, all asymmetric.
  return jwt.verify(token, publicKey, {
    algorithms: ['RS256', 'ES256'],
    audience: 'api.example.com',
    issuer: 'https://issuer.example.com/',
  });
}

module.exports = { authenticate };
