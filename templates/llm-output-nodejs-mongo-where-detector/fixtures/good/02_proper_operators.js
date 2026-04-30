// Use proper Mongo operators instead of $where.
async function findUsers(db, role, minAge) {
  return await db.collection("users").find({
    role: role,
    age: { $gte: minAge }
  }).toArray();
}
module.exports = findUsers;
