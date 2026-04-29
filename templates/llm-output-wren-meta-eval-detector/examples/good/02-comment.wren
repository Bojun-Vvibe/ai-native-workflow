// GOOD: comment mentions Meta.eval but no actual call
// Note: do NOT use Meta.eval(input) — use a parser.
class SafeParser {
  parse(s) {
    return s.split(",")
  }
}
