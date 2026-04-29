// GOOD: string literal mentions Meta.compile but no call
class Doc {
  warning() {
    return "Avoid Meta.compile(userInput) and Meta.eval(userInput)."
  }
}
