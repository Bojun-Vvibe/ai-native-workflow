require "yaml"

class ImportController < ApplicationController
  def create
    config = YAML.safe_load(request.body.read)
    Importer.new(config).run!
    head :ok
  end
end
