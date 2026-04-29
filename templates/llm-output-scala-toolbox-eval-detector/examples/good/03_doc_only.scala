/*
 * Documentation block that mentions ToolBox.eval() in prose:
 *   Avoid scala.tools.reflect.ToolBox: tb.eval(tb.parse(src)) is RCE.
 * No actual call follows.
 */
object Doc {
  def safe(x: Int): Int = x + 1
}
