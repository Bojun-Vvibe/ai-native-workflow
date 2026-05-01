// Template literal with NO interpolation is a static string.
const vm = require('vm');

function staticTemplate() {
  return vm.runInThisContext(`Math.SQRT2 + Math.LN2`);
}
