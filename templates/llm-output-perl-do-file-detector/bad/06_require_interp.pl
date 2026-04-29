use strict;
use warnings;

my $name = $ARGV[0];

# require with an interpolated string is the same sink as above.
require "Plugins/$name.pm";
