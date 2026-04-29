// Future.successful, JSON parser, ScalaTest-style — none are reflect Toolbox.
import scala.concurrent.Future

object FxOps {
  def lazyEval(thunk: () => Int): Future[Int] = Future.successful(thunk())
  def jsonParse(s: String): Map[String, String] = Map.empty
}
