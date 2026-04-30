// Bare literal — safe constant, not user input.
const two = eval("1 + 1");
const adder = new Function("a", "b", "return a + b");
const greet = new Function('return "hello"');
