// Bad fixture: template literal interpolating req.query into exec().
const { exec } = require("child_process");

function lookup(req, res) {
  exec(`whois ${req.query.domain}`, (err, stdout) => {
    res.send(stdout);
  });
}

module.exports = { lookup };
