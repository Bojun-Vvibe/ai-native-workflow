import scala.tools.reflect.ToolBox

class Sandbox {
  private val mirror = scala.reflect.runtime.currentMirror
  private val toolbox = mirror.mkToolBox()
  def compileAndRun(code: String): () => Any =
    toolbox.compile(toolbox.parse(code))
}
