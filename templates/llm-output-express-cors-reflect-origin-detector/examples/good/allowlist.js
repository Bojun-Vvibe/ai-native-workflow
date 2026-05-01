const express = require("express");
const cors = require("cors");

const app = express();

// Explicit allowlist; safe.
app.use(
  cors({
    origin: ["https://app.example.com", "https://admin.example.com"],
    credentials: true,
  })
);

app.get("/me", (req, res) => res.json({ user: req.user }));

module.exports = app;
