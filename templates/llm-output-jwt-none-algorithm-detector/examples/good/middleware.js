const jwt = require("jsonwebtoken");

function authMiddleware(req, res, next) {
  const token = req.headers.authorization.split(" ")[1];
  jwt.verify(
    token,
    process.env.JWT_PUBLIC_KEY,
    { algorithms: ["RS256"] },
    function (err, decoded) {
      if (err) return res.sendStatus(401);
      req.user = decoded;
      next();
    }
  );
}

function peekHeader(token) {
  // Decoded purely to read the kid header for key lookup; the result
  // is never trusted as authentication. Returned to a key-resolver.
  const parsed = jwt.decode(token, { complete: true });
  return parsed && parsed.header && parsed.header.kid;
}

module.exports = { authMiddleware, peekHeader };
