package example

class UserRepo {
  // Good: use Option[T] instead of returning null.
  def findById(id: Long): Option[User] = {
    val rows = query("SELECT * FROM users WHERE id = ?", id)
    rows.headOption
  }

  def firstName(id: Long): Option[String] = {
    findById(id).map(_.name)
  }
}

case class User(id: Long, name: String)
def query(sql: String, args: Any*): Seq[User] = Seq.empty
