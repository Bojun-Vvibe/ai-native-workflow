use strict;
use warnings;

my $tag = $ENV{TAG} || 'default';

# qq{} with interpolation is the same sink dressed differently
my $rv = do qq{addons/$tag/init.pl};
print $rv;
