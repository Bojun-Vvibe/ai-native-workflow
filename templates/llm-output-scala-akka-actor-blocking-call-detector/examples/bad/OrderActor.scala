package example

import akka.actor.typed.scaladsl.Behaviors
import scala.concurrent.{Await, Future}
import scala.concurrent.duration._
import java.util.concurrent.CountDownLatch

object OrderActor {
  def apply(svc: OrderSvc): Behavior[Cmd] = Behaviors.receiveMessage { msg =>
    msg match {
      case Place(id) =>
        val r = Await.ready(svc.place(id), 2.seconds)
        Behaviors.same
      case WaitFor(latch: CountDownLatch) =>
        latch.await()
        Behaviors.same
      case Pause =>
        scala.concurrent.blocking { Thread.sleep(50) }
        Behaviors.same
    }
  }
}
