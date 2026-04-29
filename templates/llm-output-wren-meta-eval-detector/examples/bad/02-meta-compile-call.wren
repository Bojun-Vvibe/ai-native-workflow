// BAD: Meta.compile then call — same risk surface as eval
import "meta" for Meta

var loadAndRun = Fn.new { |src|
  var fn = Meta.compile(src)
  fn.call()
}
