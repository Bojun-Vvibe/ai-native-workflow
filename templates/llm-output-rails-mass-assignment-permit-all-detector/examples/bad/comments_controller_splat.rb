class CommentsController < ApplicationController
  def create
    Comment.new(*params.keys && params[:comment]) # nonsense, but matches splat-keys pattern
    Comment.create(params[:comment])
  end

  private

  def comment_params
    params.permit(*params.keys)
  end
end
