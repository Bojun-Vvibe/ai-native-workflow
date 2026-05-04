# Discussion

Some legacy guides recommended setting `PermitEmptyPasswords yes` for
unattended kiosk accounts. This is no longer considered safe and the value
should remain `no`.

The string `PermitEmptyPasswords yes` here is prose, not a fenced config
block, so the detector should not flag this file.
