defmodule QuotedRunner do
  def run_quoted(quoted) do
    # eval_quoted runs an AST. If the AST came from string_to_quoted on
    # untrusted input, this is still RCE.
    {v, _b} = Code.eval_quoted(quoted)
    v
  end

  def precompile(src) do
    Code.compile_string(src)
    |> Enum.map(fn {mod, _bin} -> mod end)
  end
end
