"""os.popen with %-formatting."""
import os

handle = os.popen("grep %s /var/log/app.log" % needle)
print(handle.read())
