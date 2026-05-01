import express from "express";
import cors from "cors";

const app = express();

// Arrow-form reflector. Returns true unconditionally => reflects.
app.use(
  cors({
    origin: (origin) => true,
  })
);

// And here's the same anti-pattern with res.set instead of setHeader.
app.options("*", (req, res) => {
  res.set("Access-Control-Allow-Origin", req.headers.origin);
  res.sendStatus(204);
});

export default app;
