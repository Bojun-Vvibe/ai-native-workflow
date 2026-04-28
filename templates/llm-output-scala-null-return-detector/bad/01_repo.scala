package example

class UserRepo {
  def findById(id: Long): User = {
    val rows = query("SELECT * FROM users WHERE id = ?", id)
    if (rows.isEmpty) {
      return null
    }
    rows.head
  }
}

case class User(id: Long, name: String)
def query(sql: String, args: Any*): Seq[User] = Seq.empty
