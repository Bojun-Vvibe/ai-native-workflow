require "psych"

# Loads a config file path supplied via CLI argument.
config_path = ARGV[0] or abort("usage: run CONFIG.yml")
config = Psych.load_file(config_path)
App.boot(config)
