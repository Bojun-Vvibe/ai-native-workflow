// Not eval at all — JSON.parse is safe.
const data = JSON.parse(req.body);
const fn = someObject.evaluate(req.body); // unrelated method named evaluate
const evaluated = computeResult(req.body);
