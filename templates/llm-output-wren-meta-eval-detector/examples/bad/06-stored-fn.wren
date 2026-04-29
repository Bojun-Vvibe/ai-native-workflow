// BAD: stored Meta.compile result reused multiple times
import "meta" for Meta

var compiled = Meta.compile("System.print(42)")
compiled.call()
compiled.call()
