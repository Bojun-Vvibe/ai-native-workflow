package Calc;
use strict; use warnings;

sub safe_divide {
    my ($a, $b) = @_;
    my $r = eval {
        die "div by zero" if $b == 0;
        return $a / $b;
    };
    return (undef, $@) if $@;
    return ($r, undef);
}

1;
