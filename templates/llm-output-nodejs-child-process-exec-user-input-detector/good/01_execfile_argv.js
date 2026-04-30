// Good fixture: execFile with argv array (no shell, no concat).
const { execFile } = require("child_process");

function lookup(req, res) {
  execFile("whois", [req.query.domain], (err, stdout) => {
    res.send(stdout);
  });
}

module.exports = { lookup };
