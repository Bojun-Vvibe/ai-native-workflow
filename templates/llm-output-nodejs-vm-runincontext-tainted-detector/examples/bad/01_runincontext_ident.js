// LLM under "let users define a custom rule" pressure.
const vm = require('vm');

function evaluate(userExpr) {
  const sandbox = { result: null };
  vm.createContext(sandbox);
  vm.runInContext(userExpr, sandbox);
  return sandbox.result;
}
