const jwt = require("jsonwebtoken");

function authMiddleware(req, res, next) {
  const token = req.headers.authorization.split(" ")[1];
  // No `algorithms` option — jsonwebtoken will accept whatever the
  // header claims, including `none`.
  jwt.verify(token, process.env.JWT_SECRET, function (err, decoded) {
    if (err) return res.sendStatus(401);
    req.user = decoded;
    next();
  });
}

function trustHeader(token) {
  // .decode() does NOT verify; using the result as if it were authenticated.
  const verified = jwt.decode(token);
  return verified.sub;
}

module.exports = { authMiddleware, trustHeader };
