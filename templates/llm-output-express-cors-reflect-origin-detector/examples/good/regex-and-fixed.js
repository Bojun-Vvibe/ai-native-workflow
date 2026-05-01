const express = require("express");
const cors = require("cors");

const app = express();

// Regex allowlist for *.example.com subdomains.
app.use(
  cors({
    origin: /^https:\/\/[a-z0-9-]+\.example\.com$/,
    credentials: true,
  })
);

// Manual header set — but to a fixed origin, not reflected.
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "https://app.example.com");
  res.setHeader("Vary", "Origin");
  next();
});

module.exports = app;
