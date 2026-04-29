// BAD: Meta.compileExpression on attacker input
import "meta" for Meta

class Calculator {
  evaluate(expr) {
    var fn = Meta.compileExpression(expr)
    return fn.call()
  }
}
