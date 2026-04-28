defmodule RateLimiter do
  use GenServer

  def handle_continue(:warmup, state) do
    Process.sleep(500)  # blocks the warmup
    {:noreply, state}
  end

  # One-line callback with do: still triggers if it contains sleep.
  def handle_info(:noop, s), do: Process.sleep(1)

  def terminate(_reason, _state) do
    :timer.sleep(2_000)
    :ok
  end
end
