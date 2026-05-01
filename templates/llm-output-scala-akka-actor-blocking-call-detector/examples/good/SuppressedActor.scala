package example

import akka.actor.Actor
import scala.concurrent.Await
import scala.concurrent.duration._

// Allow-listed actor: the project owner has explicitly opted in via
// the `blocking-ok` marker because this actor runs on a dedicated
// blocking dispatcher.
class LegacyAdapterActor(legacy: LegacyClient) extends Actor {
  def receive: Receive = {
    case Lookup(id) =>
      val r = Await.result(legacy.fetch(id), 1.second) // blocking-ok
      sender() ! r
  }
}
