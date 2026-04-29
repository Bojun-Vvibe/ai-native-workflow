import scala.tools.reflect.ToolBox
import scala.reflect.runtime.universe

object Plugin {
  def load(src: String): Any = {
    val tb = universe.runtimeMirror(getClass.getClassLoader).mkToolBox()
    tb.eval(tb.parse(src))
  }
}
