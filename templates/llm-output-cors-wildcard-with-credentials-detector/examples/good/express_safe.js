# Express server, safe CORS shape: explicit origin allowlist with
# credentials, OR wildcard origin with NO credentials.
const express = require("express");
const cors = require("cors");
const app = express();

// Safe shape #1: explicit origin + credentials.
app.use(cors({
  origin: ["https://app.example.test", "https://admin.example.test"],
  credentials: true,
}));

// Safe shape #2: public read-only API; wildcard origin, no credentials.
app.use("/public", (req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  // intentionally NO Access-Control-Allow-Credentials header.
  next();
});

app.get("/me", (req, res) => res.json({ ok: true }));
app.listen(3000);
