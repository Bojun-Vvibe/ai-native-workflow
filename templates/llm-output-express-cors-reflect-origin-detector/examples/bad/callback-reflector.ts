import express from "express";
import cors from "cors";

const app = express();

// Callback-based reflector that always allows the request origin.
app.use(
  cors({
    origin: function (origin, cb) {
      // "Pass through whatever the browser sent us" — i.e. reflect.
      cb(null, true);
    },
    credentials: true,
  })
);

export default app;
