#  Overview

This h1 has two spaces after the hash. It should flag.

##   Why this matters

This h2 has three spaces. It should flag.

###    Background

This h3 has four spaces. It should flag.

## Closed heading with extra opening space  ##

This closed h2 has two spaces after the opener; should flag once.

# Heading text   #

This h1 has three spaces between text and the closing hash; should flag.

##  Both sides bad  ##

This closed h2 is bad on both sides; should produce two findings.

# Clean h1

## Clean h2

### Clean h3 ###

```
##   Inside a fence — should not flag
###     Also inside the fence
```
