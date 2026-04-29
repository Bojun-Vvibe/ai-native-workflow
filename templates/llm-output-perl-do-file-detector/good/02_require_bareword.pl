use strict;
use warnings;

# require BAREWORD is normal Perl module loading and is NOT a file-path sink.
require Carp;
require File::Spec;
require Data::Dumper;

# `use` is the compile-time form and is also fine.
use List::Util qw(sum first);

print "ok\n";
