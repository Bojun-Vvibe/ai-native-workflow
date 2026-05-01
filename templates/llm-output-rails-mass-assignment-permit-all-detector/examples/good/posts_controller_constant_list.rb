class PostsController < ApplicationController
  ALLOWED = %i[title body tag_ids].freeze

  def create
    @post = Post.create(post_params)
  end

  private

  def post_params
    params.require(:post).permit(*ALLOWED)
  end
end
