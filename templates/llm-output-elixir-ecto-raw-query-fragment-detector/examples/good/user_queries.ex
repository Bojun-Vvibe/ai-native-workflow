defmodule MyApp.UserQueries do
  import Ecto.Query
  alias MyApp.Repo

  def find_by_email(email) do
    Repo.query!("SELECT * FROM users WHERE email = $1", [email])
  end

  def delete_by_id(id) do
    Ecto.Adapters.SQL.query!(Repo, "DELETE FROM users WHERE id = $1", [id])
  end

  def search(name) do
    from(u in User, where: fragment("name = ?", ^name))
    |> Repo.all()
  end

  def healthcheck do
    Repo.query!("SELECT 1")
  end

  def by_role(role) do
    from(u in User, where: u.role == ^role) |> Repo.all()
  end
end
