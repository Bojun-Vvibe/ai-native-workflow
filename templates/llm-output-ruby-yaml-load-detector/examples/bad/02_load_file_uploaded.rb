require "yaml"

# Background job: deserialize a YAML file the user uploaded to /tmp.
class IngestJob
  def perform(upload_path)
    payload = YAML.load_file(upload_path)
    Record.create!(payload: payload)
  end
end
