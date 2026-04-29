import 'dart:mirrors';

void writeAttr(Object o, String name, Object value) {
  reflect(o).invokeSetter(Symbol(name), value);
}
