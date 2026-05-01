// Allowlisted call: explicit suppression marker on the same statement.
const vm = require('vm');

function evaluateTrustedRule(rule) {
  // The rule string is loaded from a signed, integrity-checked store.
  return vm.runInNewContext(rule, {}); // llm-allow:nodejs-vm-tainted
}
