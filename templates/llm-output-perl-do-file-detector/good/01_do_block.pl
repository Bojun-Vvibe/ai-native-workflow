use strict;
use warnings;

# `do { BLOCK }` is a control-flow construct, NOT a file load. Should not fire.
my $x = do {
    my $a = 1;
    my $b = 2;
    $a + $b;
};
print "x=$x\n";

# do { BLOCK } while (...) is also fine
my $i = 0;
do {
    $i++;
} while ($i < 3);
print "i=$i\n";
