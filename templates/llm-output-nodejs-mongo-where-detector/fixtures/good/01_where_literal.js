// $where with a static literal expression — no user input, no concat.
async function expensiveItems(db) {
  return await db.collection("items").find({
    $where: "this.price > 100"
  }).toArray();
}
module.exports = expensiveItems;
