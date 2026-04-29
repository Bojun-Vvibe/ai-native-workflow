import scala.tools.reflect.ToolBox
import scala.reflect.runtime.universe._

object UserExpr {
  val tb = scala.reflect.runtime.currentMirror.mkToolBox()
  def run(src: String): Any = tb.eval(tb.parse(src))
}
