// BAD: direct Meta.eval on user-derived string
import "meta" for Meta

class Runner {
  static run(src) {
    Meta.eval(src)
  }
}
