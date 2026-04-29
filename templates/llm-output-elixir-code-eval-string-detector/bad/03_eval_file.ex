defmodule ConfigLoader do
  # LLM "shortcut" for parsing config files: just eval them.
  def load(path) do
    Code.eval_file(path)
  end

  def load_compiled(path) do
    Code.compile_file(path)
  end
end
