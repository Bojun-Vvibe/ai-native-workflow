// Bad fixture: bare user-input identifier passed as the command.
const { exec } = require("child_process");

function run(userInput) {
  exec(userInput, (err, stdout) => {
    if (err) throw err;
    process.stdout.write(stdout);
  });
}

module.exports = { run };
