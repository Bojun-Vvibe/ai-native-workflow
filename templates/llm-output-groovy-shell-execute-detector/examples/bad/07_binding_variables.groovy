def filename = binding.variables['file']
Runtime.getRuntime().exec("/usr/bin/cat " + filename)
