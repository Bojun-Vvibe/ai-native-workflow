// Fixtures for the JS eval-injection detector. These are intentionally
// vulnerable patterns the detector must flag. They are NOT exploits —
// no payloads, no IO, just the call shape.

// Finding 1: bare eval of identifier.
function f1(userInput) {
  return eval(userInput);
}

// Finding 2: eval with string concat.
function f2(userInput) {
  return eval("var x = " + userInput);
}

// Finding 3: eval with template literal interpolation.
function f3(expr) {
  return eval(`return ${expr};`);
}

// Finding 4: window.eval.
function f4(input) {
  return window.eval(input);
}

// Finding 5: globalThis.eval.
function f5(input) {
  return globalThis.eval(input);
}

// Finding 6: new Function with dynamic body.
function f6(body) {
  return new Function("x", "y", body);
}

// Finding 7: new Function with single dynamic arg.
function f7(req) {
  return new Function(req.body.code);
}

// Finding 8: eval with member access.
function f8(req) {
  return eval(req.body.code);
}

// Finding 9: eval with concatenated template (interpolation form).
function f9(name) {
  return eval(`hello_${name}()`);
}
