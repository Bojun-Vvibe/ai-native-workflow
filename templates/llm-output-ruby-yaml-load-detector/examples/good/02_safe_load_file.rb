require "yaml"

class IngestJob
  def perform(upload_path)
    payload = YAML.safe_load_file(upload_path)
    Record.create!(payload: payload)
  end
end
