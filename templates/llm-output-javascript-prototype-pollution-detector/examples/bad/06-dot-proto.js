// .__proto__ chained write -- another sink shape.
function taint(obj) {
  obj.__proto__.tainted = 1;
}
taint({});
