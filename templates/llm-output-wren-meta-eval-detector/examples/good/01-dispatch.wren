// GOOD: dispatch table, no eval
class Dispatcher {
  static run(name, args) {
    var handlers = { "add": Fn.new { |a, b| a + b }, "sub": Fn.new { |a, b| a - b } }
    return handlers[name].call(args[0], args[1])
  }
}
