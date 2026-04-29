import 'dart:mirrors';

dynamic readAttr(Object target, String attr) {
  final m = reflect(target);
  return m.invokeGetter(Symbol(attr));
}
