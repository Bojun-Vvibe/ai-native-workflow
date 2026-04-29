# bad.raku — every EVAL pattern the detector should catch.
# Run:  python3 detect.py examples/bad.raku
use MONKEY-SEE-NO-EVAL;                       # bad-1: gating pragma

sub run-user-snippet($s) {
    EVAL $s;                                   # bad-2: bareword EVAL
}

sub run-with-paren($s) {
    EVAL($s);                                  # bad-3: call form
}

sub run-with-lang($s) {
    EVAL $s, :lang<Perl5>;                     # bad-4: cross-lang EVAL
}

sub run-method($expr) {
    $expr.EVAL;                                # bad-5: method form
}

sub run-from-file($path) {
    EVALFILE $path;                            # bad-6: file EVAL
}

sub run-via-compiler($s) {
    $*W.compile($s);                           # bad-7: reflective compile
}

sub run-via-repl($s) {
    $*REPL.eval($s);                           # bad-8: REPL.eval
}

sub run-lc-eval($s) {
    eval "$s";                                  # bad-9: lowercase eval-string
}

# umbrella pragma form too
use MONKEY;                                    # bad-10: umbrella pragma
