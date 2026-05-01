defmodule MyApp.UserQueries do
  import Ecto.Query
  alias MyApp.Repo

  def find_by_email(email) do
    Repo.query!("SELECT * FROM users WHERE email = '" <> email <> "'")
  end

  def delete_by_id(id) do
    Ecto.Adapters.SQL.query!(Repo, "DELETE FROM users WHERE id = " <> id, [])
  end

  def search(name) do
    from(u in User, where: fragment("name = '#{name}'"))
    |> Repo.all()
  end

  def raw(sql) do
    Repo.query!(sql)
  end

  def by_role(role) do
    Ecto.Adapters.SQL.query!(Repo, "SELECT id FROM users WHERE role = '#{role}'")
  end
end
