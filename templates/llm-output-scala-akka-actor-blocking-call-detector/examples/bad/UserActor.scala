package example

import akka.actor.Actor
import scala.concurrent.Await
import scala.concurrent.duration._

class UserActor(repo: UserRepo) extends Actor {
  def receive: Receive = {
    case FetchUser(id) =>
      val user = Await.result(repo.find(id), 5.seconds)
      sender() ! user
    case Heartbeat =>
      Thread.sleep(100)
      sender() ! Pong
    case Drain(q) =>
      val item = q.take()
      sender() ! item
    case Slow =>
      Thread.sleep(500)
      sender() ! Done
  }
}
