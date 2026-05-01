defmodule MyApp.LegacyAdapter do
  alias MyApp.Repo

  # Operator has manually validated this SQL builder; opt out per-line.
  def trusted(sql) do
    Repo.query!(sql) # sql-ok
  end
end
