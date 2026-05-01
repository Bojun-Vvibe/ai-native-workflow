// Safe deepMerge: explicit guard against __proto__/constructor/prototype.
function deepMerge(target, src) {
  for (const key in src) {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
      continue;
    }
    if (typeof src[key] === 'object' && src[key] !== null) {
      if (!target[key]) target[key] = {};
      deepMerge(target[key], src[key]);
    } else {
      target[key] = src[key];
    }
  }
  return target;
}

deepMerge({}, JSON.parse(input));
