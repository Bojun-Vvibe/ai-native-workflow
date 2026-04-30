const vm = require('vm');
function dynamic(input) {
  return vm.runInNewContext(`return ${input}`, {});
}
