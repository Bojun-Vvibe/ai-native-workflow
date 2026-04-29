// Regex compile, no reflect Toolbox.
import scala.util.matching.Regex

object Patterns {
  val rx: Regex = "[a-z]+".r
  def find(s: String): Option[String] = rx.findFirstIn(s)
}
