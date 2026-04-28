class LazyDefaults {
  // All `late` fields here have initializers — this is the legitimate
  // lazy-evaluation pattern.
  late final String greeting = 'hello, ${who()}';
  late final List<int> primes = computePrimes(100);

  String who() => 'world';
  List<int> computePrimes(int n) => <int>[2, 3, 5, 7];
}
