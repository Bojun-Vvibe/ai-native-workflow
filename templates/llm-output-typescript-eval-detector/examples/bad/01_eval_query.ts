// LLM-typical: parse JSON expression from query string by eval'ing it.
import express from "express";
const app = express();

app.get("/calc", (req, res) => {
  const expr = req.query.expr as string;
  const result = eval(expr);
  res.json({ result });
});
