// Mongoose .$where() helper called with a variable.
async function search(model, expr) {
  return model.$where(expr).exec();
}
module.exports = search;
