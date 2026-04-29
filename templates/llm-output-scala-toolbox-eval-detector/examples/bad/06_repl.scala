import scala.tools.reflect.ToolBox

object Repl {
  private val toolbox =
    scala.reflect.runtime.currentMirror.mkToolBox()

  def line(input: String): String = {
    val out = toolbox.compile(toolbox.parse(input))()
    out.toString
  }
}
