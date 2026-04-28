package example

object Cache {
  private val store = scala.collection.mutable.Map.empty[String, String]

  def get(key: String): String = {
    if (store.contains(key)) store(key)
    else null
  }

  def firstOrNull(items: Seq[String]): String = {
    if (items.nonEmpty) items.head else null
  }
}
