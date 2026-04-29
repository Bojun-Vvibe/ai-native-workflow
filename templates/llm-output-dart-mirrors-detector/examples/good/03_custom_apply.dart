// A user-defined `apply` method on a custom class. No mirrors imported,
// no reflect() anywhere. Calling .apply on iterables / functors is fine.
class Pipe<T> {
  final T Function(T) f;
  Pipe(this.f);
  T apply(T x) => f(x);
}

void main() {
  final p = Pipe<int>((x) => x + 1);
  print(p.apply(41));
  // Iterable.fold-style usage of `.apply(` on local objects is benign.
}
