// No vm at all — the detector should not flag JSON.parse / Function.
function compute(input) {
  const data = JSON.parse(input);
  return data.value * 2;
}
module.exports = { compute };
