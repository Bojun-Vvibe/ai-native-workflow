class Cart {
  late int total;
  late List<String> skus;

  void load(int t, List<String> s) {
    total = t;
    skus = s;
  }
}
