// constructor.prototype write -- equivalent to __proto__ pollution.
function pollute(obj, key, value) {
  obj.constructor.prototype[key] = value;
}
pollute({}, 'isAdmin', true);
