const vm = require('node:vm');

function buildAndRun(name) {
  const fn = vm.compileFunction(`return ${name}.toUpperCase();`, ['name']);
  return fn(name);
}
