# good.raku — patterns that look EVAL-ish but are safe.
# Run:  python3 detect.py examples/good.raku  (expect 0 findings)

# 1) Block-form `eval` is exception trapping in Perl 5; in Raku we
#    use `try { ... }`. No string EVAL.
sub safe-try {
    try {
        risky-thing();
        CATCH { default { say "caught: " ~ .message } }
    }
}

# 2) Dispatch via a hash of code refs — the idiomatic replacement
#    for "look up a function by name and run it".
my %dispatch =
    add => -> $a, $b { $a + $b },
    sub => -> $a, $b { $a - $b };

sub safe-dispatch($op, $a, $b) {
    %dispatch{$op}.($a, $b)
}

# 3) Mention of EVAL inside a string literal — must not trigger.
my $doc = "To run user code you would call EVAL \$s, but DON'T.";
my $doc2 = 'EVAL is dangerous';
my $doc3 = q[EVAL inside q-brackets];
my $doc4 = Q{EVAL inside Q-braces};

# 4) Mention of EVAL inside a `#` comment — must not trigger.
# Avoid EVAL $user-input at all costs. Avoid .EVAL too.

# 5) Mention inside a pod block — must not trigger.
=begin pod
You might be tempted to write `EVAL $s` here. Don't. Also `EVALFILE`
and `$*W.compile($s)` are listed only as cautionary examples.
=end pod

# 6) Suppression — a unit-test helper that round-trips a known-safe
#    internal sexpr-ish blob, justified inline.
sub roundtrip-internal($literal) {
    EVAL $literal;   # eval-string-ok — fixture only, never reaches user input
}

# 7) Identifier that *contains* `eval` as a substring is fine.
sub evaluator-stats { 42 }
my $eval-count = 0;
$eval-count++;
say evaluator-stats() + $eval-count;
