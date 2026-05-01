class PostsController < ApplicationController
  def create
    @post = Post.create(post_params)
  end

  private

  def post_params
    # LLM-generated "convenience" helper that just forwards every key.
    params.require(:post).permit(params[:post].keys)
  end
end
