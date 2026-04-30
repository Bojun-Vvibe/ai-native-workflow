// mapReduce called with a function reference, not a JS-as-string built from input.
const mapFn = function () { /* uses fixed field */ return 1; };
const reduceFn = function (k, v) { return v.length; };
async function run(coll) {
  return await coll.mapReduce(mapFn, reduceFn, { out: { inline: 1 } });
}
module.exports = run;
