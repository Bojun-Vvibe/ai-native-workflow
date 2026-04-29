// BAD: building source from concatenation, then Meta.eval
import "meta" for Meta

class Plugin {
  static load(name, body) {
    var src = "var %(name) = Fn.new { %(body) }"
    Meta.eval(src)
  }
}
