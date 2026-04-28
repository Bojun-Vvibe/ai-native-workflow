defmodule Good.Docs do
  @moduledoc """
  Do NOT call Process.sleep inside handle_call — it blocks the
  mailbox. The example below is in a heredoc and must not be flagged:

      def handle_call(:bad, _from, s) do
        Process.sleep(1000)
        {:reply, :ok, s}
      end
  """

  # A string literal mentioning Process.sleep must not be flagged.
  def banner, do: "Process.sleep is forbidden inside :timer.sleep too"

  # Sigil with a sleep mention.
  def sample, do: ~s|handle_info -> Process.sleep(10)|
end
