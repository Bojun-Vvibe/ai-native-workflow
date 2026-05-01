const express = require("express");
const cors = require("cors");

const app = express();

// origin: true reflects the request Origin and combined with
// credentials: true makes every authenticated cross-origin request
// readable by any third-party site.
app.use(
  cors({
    origin: true,
    credentials: true,
  })
);

app.get("/me", (req, res) => res.json({ user: req.user }));

module.exports = app;
