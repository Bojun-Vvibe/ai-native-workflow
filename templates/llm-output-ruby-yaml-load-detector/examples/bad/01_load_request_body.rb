require "yaml"

class ImportController < ApplicationController
  def create
    # LLM-generated: parse user-uploaded YAML straight into objects.
    config = YAML.load(request.body.read)
    Importer.new(config).run!
    head :ok
  end
end
