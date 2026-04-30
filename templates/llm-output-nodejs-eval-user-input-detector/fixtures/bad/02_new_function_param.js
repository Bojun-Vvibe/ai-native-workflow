function runUserCode(code) {
  return new Function(code)();
}
