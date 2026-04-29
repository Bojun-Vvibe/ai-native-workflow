use strict;
use warnings;

my $mod_path = "/var/spool/uploads/user.pm";
# require with a scalar runs arbitrary file at runtime
require $mod_path;
print "loaded\n";
