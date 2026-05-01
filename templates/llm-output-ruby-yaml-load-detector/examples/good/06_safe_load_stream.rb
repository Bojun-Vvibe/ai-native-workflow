require "yaml"

# Multi-doc stream parsed safely.
def handle_webhook(body)
  YAML.safe_load_stream(body, permitted_classes: [Time, Date]) do |doc|
    process(doc)
  end
end
