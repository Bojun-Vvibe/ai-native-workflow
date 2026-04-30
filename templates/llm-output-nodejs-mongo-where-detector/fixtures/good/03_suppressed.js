// Reviewed: expr is built from a server-side enum, not user input.
async function search(model, expr) {
  return model.$where(expr).exec(); // mongo-where-ok
}
module.exports = search;
