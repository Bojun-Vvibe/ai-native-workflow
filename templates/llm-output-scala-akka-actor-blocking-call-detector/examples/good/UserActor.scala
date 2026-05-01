package example

import akka.actor.Actor
import akka.pattern.pipe
import scala.concurrent.ExecutionContext

class UserActor(repo: UserRepo)(implicit ec: ExecutionContext) extends Actor {
  def receive: Receive = {
    case FetchUser(id) =>
      repo.find(id).pipeTo(sender())
    case Heartbeat =>
      sender() ! Pong
  }
}
