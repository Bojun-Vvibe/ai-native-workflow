// Object.keys + forEach recursive copy -- same flaw as deepMerge.
function assignDeep(dst, src) {
  Object.keys(src).forEach(function (k) {
    if (src[k] && typeof src[k] === 'object') {
      dst[k] = dst[k] || {};
      assignDeep(dst[k], src[k]);
    } else {
      dst[k] = src[k];
    }
  });
}

const body = JSON.parse(req.rawBody);
assignDeep(config, body);
