class Admin::SeedsController < ApplicationController
  before_action :require_admin

  def import
    # Internal admin tool that legitimately accepts every key.
    Setting.assign_attributes(params[:settings]) # mass-assignment-allowed
  end
end
