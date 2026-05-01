require "yaml"

# Psych >= 4: passing permitted_classes makes load behave safely.
def parse(body)
  YAML.load(body,
            permitted_classes: [Symbol, Time, Date],
            aliases: false)
end
