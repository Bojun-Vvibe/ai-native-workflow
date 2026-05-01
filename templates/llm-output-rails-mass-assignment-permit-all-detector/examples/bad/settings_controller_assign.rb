class SettingsController < ApplicationController
  def bulk_update
    Setting.assign_attributes(params[:settings])
    Setting.save
  end

  def admin_passthrough
    params[:user].permit!
  end
end
