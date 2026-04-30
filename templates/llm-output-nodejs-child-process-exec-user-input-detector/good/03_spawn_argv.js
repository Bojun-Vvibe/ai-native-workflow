// Good fixture: spawn() with argv array; user input never hits a shell.
const { spawn } = require("child_process");

function ping(host, onLine) {
  // Note: even though `host` is user-supplied, spawn() with an argv
  // array does not invoke a shell, so there is no injection surface.
  const child = spawn("ping", ["-c", "1", host]);
  child.stdout.on("data", onLine);
  return child;
}

module.exports = { ping };
