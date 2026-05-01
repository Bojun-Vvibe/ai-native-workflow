require "yaml"

# Multi-doc YAML stream from an HTTP webhook payload.
def handle_webhook(body)
  YAML.load_stream(body) do |doc|
    process(doc)
  end
end
