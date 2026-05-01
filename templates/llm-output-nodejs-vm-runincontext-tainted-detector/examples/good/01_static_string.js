// Static literal: detector should leave it alone.
const vm = require('vm');

function helloOnce() {
  return vm.runInNewContext("Math.PI", {});
}
