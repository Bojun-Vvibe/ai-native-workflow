// Block comment / docstring mention only — never executed.
/*
 * Anti-pattern reference:
 *   db.collection("x").find({ $where: "this.role === '" + role + "'" })
 * Do not do this. We use proper operators instead.
 */
function noop() {
  return null;
}
module.exports = noop;
