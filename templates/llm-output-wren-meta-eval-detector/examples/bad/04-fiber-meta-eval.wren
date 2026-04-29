// BAD: Meta.eval inside a fiber — still RCE
import "meta" for Meta

var f = Fiber.new {
  Meta.eval("System.print(\"pwn\")")
}
f.call()
