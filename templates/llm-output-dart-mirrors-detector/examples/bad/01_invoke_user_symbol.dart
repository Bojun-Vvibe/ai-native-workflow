// Reflective dispatch on user-supplied method name.
import 'dart:mirrors';

class Service {
  void ping() {}
  void shutdown() {}
}

void run(String userMethod, List args) {
  final m = reflect(Service());
  m.invoke(Symbol(userMethod), args);
}
