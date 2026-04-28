class Mixed {
  late final Repo repo;
  // The next line has an initializer and must NOT be flagged.
  late final cached = expensiveCompute();

  String expensiveCompute() => 'computed';
}

class Repo {}
