// $where with a template literal that interpolates user input.
export async function findUsers(db, role) {
  return db.collection("users").find({
    "$where": `this.role === '${role}'`
  }).toArray();
}
