// Function.apply with attacker-shaped arg list -- still arbitrary call.
dynamic call(Function fn, List positional, Map<Symbol, dynamic> named) {
  return Function.apply(fn, positional, named);
}
