import 'dart:mirrors';

Object? construct(String className, List positional) {
  final lib = currentMirrorSystem().findLibrary(Symbol('app'));
  final cm = lib.declarations[Symbol(className)] as ClassMirror;
  return cm.newInstance(Symbol(''), positional).reflectee;
}
