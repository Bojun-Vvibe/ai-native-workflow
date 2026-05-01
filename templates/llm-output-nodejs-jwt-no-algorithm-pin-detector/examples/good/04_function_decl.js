// GOOD: this file declares a *function* called verify -- not a call site
// for jsonwebtoken.verify. Detector must not flag declarations.

function verify(token, key) {
  // toy verifier; never actually called against jsonwebtoken
  if (!token || !key) throw new Error('missing');
  return { ok: true };
}

module.exports = { verify };
