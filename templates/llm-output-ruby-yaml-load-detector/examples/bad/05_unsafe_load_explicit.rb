require "yaml"

# An LLM-suggested "fix" for Psych 4 deprecation that just papered
# over it by calling unsafe_load instead of switching to safe_load.
class SettingsLoader
  def self.from(io)
    YAML.unsafe_load(io.read)
  end
end
