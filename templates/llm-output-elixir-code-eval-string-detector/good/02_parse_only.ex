defmodule ParseOnly do
  @moduledoc """
  Parses but does not execute. `Code.string_to_quoted` returns an AST;
  we then walk it ourselves. This is the safe pattern and must not be
  flagged. Mentioning `Code.eval_string` inside a comment must also not
  be flagged.
  """

  # Note: do NOT call Code.eval_string here, ever.
  def parse(src) do
    case Code.string_to_quoted(src) do
      {:ok, ast} -> {:ok, walk(ast)}
      err -> err
    end
  end

  defp walk({op, _, args}) when is_list(args), do: {op, Enum.map(args, &walk/1)}
  defp walk(other), do: other
end
