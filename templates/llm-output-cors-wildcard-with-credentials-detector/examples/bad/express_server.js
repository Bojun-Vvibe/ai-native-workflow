// Express server with the broken CORS combo (header form + shorthand).
const express = require("express");
const cors = require("cors");
const app = express();

// Bad shape #1: explicit headers, wildcard origin + credentials true.
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Credentials", "true");
  next();
});

// Bad shape #2: cors() shorthand bundling both.
app.use(cors({ origin: "*", credentials: true }));

// Bad shape #3: origin: true reflects every origin (equivalent risk).
app.use(cors({ origin: true, credentials: true }));

app.get("/me", (req, res) => res.json({ ok: true }));
app.listen(3000);
