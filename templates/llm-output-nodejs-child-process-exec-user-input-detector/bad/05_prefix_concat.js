// Bad fixture: user input prefix-concatenated to a literal flag string.
const { exec } = require("child_process");

function archive(filename) {
  exec(filename + " | tar -czf out.tgz -", (err) => {
    if (err) console.error(err);
  });
}

module.exports = { archive };
