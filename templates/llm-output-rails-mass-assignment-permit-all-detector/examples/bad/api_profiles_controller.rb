class Api::V1::ProfilesController < ApplicationController
  def update
    profile = Profile.find(params[:id])
    profile.update(params[:profile])
    render json: profile
  end
end
