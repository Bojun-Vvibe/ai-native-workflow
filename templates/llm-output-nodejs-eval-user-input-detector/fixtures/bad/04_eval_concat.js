const userExpr = req.query.q;
const out = eval("(" + userExpr + ")");
