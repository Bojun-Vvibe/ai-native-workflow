// Safe: Object.create(null) -- result has no prototype to pollute.
function makeBag() {
  return Object.create(null);
}

const bag = makeBag();
for (const k of Object.keys(input)) {
  bag[k] = input[k];
}
