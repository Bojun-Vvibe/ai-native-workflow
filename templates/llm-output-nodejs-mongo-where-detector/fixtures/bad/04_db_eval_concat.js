// Deprecated db.eval(...) called with attacker-controlled JS string.
async function adminEval(db, payload) {
  return await db.eval("function() { return " + payload + "; }");
}
module.exports = adminEval;
