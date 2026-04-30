"""os.system with .format injection."""
import os

os.system("rm {}".format(path))
