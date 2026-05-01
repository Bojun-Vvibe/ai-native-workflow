// Safe dotted-path setter: explicit denylist + hasOwnProperty.call check.
function setByPath(obj, path, value) {
  const parts = path.split('.');
  for (const p of parts) {
    if (p === '__proto__' || p === 'constructor' || p === 'prototype') {
      throw new Error('forbidden key');
    }
  }
  let current = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!Object.prototype.hasOwnProperty.call(current, parts[i])) {
      current[parts[i]] = Object.create(null);
    }
    current = current[parts[i]];
  }
  current[parts[parts.length - 1]] = value;
}
