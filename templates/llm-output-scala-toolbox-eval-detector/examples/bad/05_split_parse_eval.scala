import scala.tools.reflect.ToolBox
import scala.reflect.runtime.{universe => u}

class ScriptHost {
  val tb = u.runtimeMirror(getClass.getClassLoader).mkToolBox()
  // separate parse/eval for clearer error messages
  def execute(code: String): Any = {
    val tree = tb.parse(code)
    val result = tb.eval(tree)
    result
  }
}
