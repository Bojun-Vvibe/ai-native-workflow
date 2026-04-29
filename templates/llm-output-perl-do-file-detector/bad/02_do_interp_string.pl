use strict;
use warnings;

my $name = shift;
# interpolated path -> RCE if $name is attacker-controlled
my $rv = do "plugins/$name.pl";
print $rv, "\n";
