// Bad fixture: string concatenation with req.body.
const child_process = require("child_process");

function rename(req, res) {
  child_process.exec("mv /tmp/upload " + req.body.target, (err) => {
    if (err) return res.status(500).end();
    res.send("ok");
  });
}

module.exports = { rename };
