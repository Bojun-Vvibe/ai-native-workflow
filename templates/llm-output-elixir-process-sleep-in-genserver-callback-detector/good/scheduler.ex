defmodule Good.Scheduler do
  use GenServer

  # Sleep is fine outside callbacks — e.g. in helper functions called
  # from non-GenServer code, or in tests.
  def helper_for_tests do
    Process.sleep(10)
    :ok
  end

  # Inside a callback, schedule with send_after instead of blocking.
  def handle_call(:tick, _from, state) do
    Process.send_after(self(), :work, 50)
    {:reply, :ok, state}
  end

  # handle_continue defers work without blocking the mailbox.
  def init(opts) do
    {:ok, opts, {:continue, :setup}}
  end

  def handle_continue(:setup, state) do
    # No sleep here.
    {:noreply, state}
  end
end
