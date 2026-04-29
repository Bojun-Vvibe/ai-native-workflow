import scala.tools.reflect.{ToolBox, ToolBoxError}

object RuleEngine {
  val cm = scala.reflect.runtime.currentMirror
  val tb = cm.mkToolBox()
  def evalRule(rule: String): Boolean = {
    val tree = tb.parse(s"($rule): Boolean")
    tb.eval(tree).asInstanceOf[Boolean]
  }
}
