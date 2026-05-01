require "json"

# Prefer JSON for cross-trust-boundary payloads. No deserialization gadget.
class ImportController < ApplicationController
  def create
    config = JSON.parse(request.body.read)
    Importer.new(config).run!
    head :ok
  end
end
