// GOOD: this file does not import jsonwebtoken and does not use the
// conventional jwt/JWT identifiers. Detector must stay silent.

const crypto = require('crypto');

function checksum(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

module.exports = { checksum };
