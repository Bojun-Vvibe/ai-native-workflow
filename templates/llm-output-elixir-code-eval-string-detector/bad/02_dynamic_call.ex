defmodule DynamicCall do
  def call_named(name, args) do
    # Looks "convenient" but is RCE if `name` is attacker-controlled.
    src = "MyMod.#{name}(#{inspect(args)})"
    {value, _} = Code.eval_string(src)
    value
  end
end
