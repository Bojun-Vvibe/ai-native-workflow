package example

// The word "null" appears in comments and strings here, but never as
// an actual return value. The detector must not flag any of this.
object Talk {
  def describe(s: String): String = {
    // Note: we intentionally never return null from this function.
    val msg = "the literal token null is a footgun in Scala"
    val tag = """multi-line
                 string mentioning null inside it"""
    msg + " " + tag
  }

  def either(flag: Boolean): Either[String, Int] = {
    if (flag) Right(1) else Left("error: returned no value (not null)")
  }

  def safeHead(xs: Seq[Int]): Option[Int] = xs.headOption
}
