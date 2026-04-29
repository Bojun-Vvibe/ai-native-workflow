use strict;
use warnings;

# String constants documenting the danger should not trigger the detector.
my @TIPS = (
    "tip: never call do \$path on user input",
    "tip: avoid require \"Plugins/\$name.pm\"",
    "tip: do qq{addons/\$tag.pl} is the same RCE",
);

print join("\n", @TIPS), "\n";
