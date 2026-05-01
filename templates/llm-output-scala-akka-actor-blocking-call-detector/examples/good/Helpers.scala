package example

import scala.concurrent.Await
import scala.concurrent.duration._

// Plain utility object — no actor handler in this file. Blocking is
// fine here because it's not on an actor dispatcher.
object Helpers {
  def syncFetch[A](f: scala.concurrent.Future[A]): A =
    Await.result(f, 10.seconds)

  def naptime(): Unit = Thread.sleep(25)
}
