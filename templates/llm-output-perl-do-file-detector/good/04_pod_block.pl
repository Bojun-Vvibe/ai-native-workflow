use strict;
use warnings;

=head1 SAFETY NOTES

This POD block names every dangerous form on purpose:

    do $path
    do "plugins/$name.pl"
    do qq{addons/$tag.pl}
    require $mod_path
    require "Plugins/$name.pm"

The masker should hide all of them.

=cut

sub add { return $_[0] + $_[1] }
print add(2, 3), "\n";
