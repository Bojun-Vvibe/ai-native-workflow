const jwt = require('jsonwebtoken');

function authenticate(token, key, cb) {
  // BAD: callback form, but no options object means no algorithms pin.
  jwt.verify(token, key, function (err, decoded) {
    if (err) return cb(err);
    cb(null, decoded);
  });
}

module.exports = { authenticate };
