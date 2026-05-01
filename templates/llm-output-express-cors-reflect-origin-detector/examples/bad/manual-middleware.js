const express = require("express");

const app = express();

// Manual reflection done by hand — same problem, no `cors` package
// involved. The Allow-Credentials header below upgrades this finding.
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", req.headers.origin);
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST");
  next();
});

app.get("/profile", (req, res) => res.json({ ok: true }));

module.exports = app;
