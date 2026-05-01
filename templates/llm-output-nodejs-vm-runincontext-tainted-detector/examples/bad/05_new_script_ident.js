const vm = require('vm');

function makeScript(snippet) {
  const script = new vm.Script(snippet);
  return script.runInThisContext();
}
