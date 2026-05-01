class AccountsController < ApplicationController
  def update
    @account = current_user.account
    @account.update(params[:account])
    redirect_to @account
  end
end
