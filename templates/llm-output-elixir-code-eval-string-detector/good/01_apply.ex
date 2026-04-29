defmodule SafeDispatch do
  @doc """
  Dispatch by name using `apply/3` and an explicit allowlist.
  This is the correct pattern; it must NOT trigger the detector
  even though the docstring contains the word `Code.eval_string`
  inside a heredoc.
  """
  @allowed ~w(add sub mul)a

  def call(name, args) when is_atom(name) and is_list(args) do
    if name in @allowed do
      apply(__MODULE__, name, args)
    else
      {:error, :forbidden}
    end
  end

  def add(a, b), do: a + b
  def sub(a, b), do: a - b
  def mul(a, b), do: a * b
end
