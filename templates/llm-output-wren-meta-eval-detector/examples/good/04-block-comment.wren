/*
  GOOD: block comment with the words Meta.eval and Meta.compile inside.
  These should not be flagged because the masker zeroes the comment body.
  Meta.eval("nope") Meta.compile("also nope")
*/
class Quiet {
  noop() {}
}
