defmodule UserScript do
  def run(input) do
    # LLM-emitted: take a string from the request and Code.eval_string it.
    {result, _binding} = Code.eval_string(input)
    result
  end
end
