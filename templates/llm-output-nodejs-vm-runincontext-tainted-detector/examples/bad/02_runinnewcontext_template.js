const vm = require('vm');

module.exports = function (input) {
  return vm.runInNewContext(`return ${input};`, { input });
};
