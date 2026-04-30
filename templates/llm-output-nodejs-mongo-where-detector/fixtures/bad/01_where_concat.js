// Express-style handler: $where built from request query.
async function findItems(req, db) {
  const minPrice = req.query.min;
  return await db.collection("items").find({
    $where: "this.price > " + minPrice
  }).toArray();
}
module.exports = findItems;
