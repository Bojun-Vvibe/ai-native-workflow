// Identifier-name only LOOKS like a vm method, but is a method on a
// different object. Detector keys on `vm.<method>` or a bare named
// import; this is a custom class and should not be flagged.
class Compiler {
  runInNewContext(input) {
    return this.parse(input);
  }
  parse(s) { return s.length; }
}

const c = new Compiler();
c.runInNewContext("hello");  // method call on Compiler, not vm
