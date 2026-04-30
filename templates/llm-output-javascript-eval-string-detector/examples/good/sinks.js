// Safe fixtures. Detector must NOT flag any line in this file.

// Static literal — bad style but not injection.
function g1() {
  return eval("1 + 1");
}

// new Function with fully static body — not injection.
function g2() {
  return new Function("x", "y", "return x + y;");
}

// new Function with no args — harmless.
function g3() {
  return new Function();
}

// JSON.parse is the right tool — not eval.
function g4(text) {
  return JSON.parse(text);
}

// setTimeout with a function reference (not a string) — not eval.
function g5(fn) {
  return setTimeout(fn, 1000);
}

// Suppressed audited call.
function g6(input) {
  return eval(input); // llm-allow:js-eval-dynamic
}

// Comment containing fake eval — must not fire.
// eval(userInput);

// String literal containing the call shape — must not fire.
const EXAMPLE = "eval(userInput);";

// Identifier named eval-like but not the global — `myEval(x)` is not eval.
function g7(myEval, x) {
  return myEval(x);
}

// Template with no interpolation passed to eval — static literal.
function g8() {
  return eval(`return 42;`);
}

// new Function as a property of a custom object — not the constructor.
const obj = { Function: function(s) { return s; } };
function g9(input) {
  return obj.Function(input);
}
