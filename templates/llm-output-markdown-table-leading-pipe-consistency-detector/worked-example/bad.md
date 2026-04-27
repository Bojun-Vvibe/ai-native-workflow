# Status report

## Clean table (uniform, no leading pipes)

name | status | owner
---- | ------ | -----
alpha | green | team-a
beta | yellow | team-b
gamma | green | team-a

## Mixed table (this should fire)

| name | status | owner
| ---- | ------ | -----
| alpha | green | team-a
beta | yellow | team-b
| gamma | green | team-a
delta | red | team-c

## Notes

The mixed table above blends leading-pipe rows with no-leading-pipe rows,
which is the defect this detector flags.
