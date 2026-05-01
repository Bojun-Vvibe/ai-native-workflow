// Classic unsafe deepMerge -- attacker payload {"__proto__":{"isAdmin":true}}
// pollutes Object.prototype.
function deepMerge(target, src) {
  for (const key in src) {
    if (typeof src[key] === 'object' && src[key] !== null) {
      if (!target[key]) target[key] = {};
      deepMerge(target[key], src[key]);
    } else {
      target[key] = src[key];
    }
  }
  return target;
}

const userInput = JSON.parse(process.argv[2]);
deepMerge({}, userInput);
