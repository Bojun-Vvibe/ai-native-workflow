import express from "express";
import cors from "cors";

const ALLOWED = new Set([
  "https://app.example.com",
  "https://admin.example.com",
]);

const app = express();

// Callback-based, but it actually checks the origin against an
// allowlist before approving — this is the safe pattern.
app.use(
  cors({
    origin: function (origin, cb) {
      if (!origin) return cb(null, false);
      if (ALLOWED.has(origin)) return cb(null, origin);
      return cb(new Error("origin not allowed"));
    },
    credentials: true,
  })
);

export default app;
