class StringsAndComments {
  // The string "late String foo;" must not trigger the detector.
  static const tip = 'avoid late String foo; without an initializer';

  static const code = '''
    class Bad {
      late int x;
    }
  ''';

  /* Block comment: late final Repo repo; */
  // line comment: late String name;

  late final String greeting = 'computed: $tip';
}
