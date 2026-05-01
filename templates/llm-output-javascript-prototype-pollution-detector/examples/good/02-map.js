// Safe: uses a Map so prototype is not in the lookup chain.
const cache = new Map();
function set(key, value) {
  cache.set(key, value);
}
set('user.name', 'alice');
