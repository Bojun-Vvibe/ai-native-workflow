use strict;
use warnings;
use File::Spec;

# Safe alternative: use a hard-coded plugin registry, never a runtime path.
my %PLUGINS = (
    greet => sub { "hello, $_[0]" },
    bye   => sub { "goodbye, $_[0]" },
    ping  => sub { "pong" },
);

sub dispatch {
    my ($name, @args) = @_;
    my $fn = $PLUGINS{$name} or die "unknown plugin: $name";
    return $fn->(@args);
}

print dispatch("greet", "world"), "\n";
