// Good fixture: exec() with a fully literal command string, no input.
const { exec } = require("child_process");

function uptime(cb) {
  exec("uptime", cb);
}

module.exports = { uptime };
