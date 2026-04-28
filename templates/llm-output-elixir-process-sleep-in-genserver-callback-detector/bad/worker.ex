defmodule Worker do
  use GenServer

  def init(opts) do
    Process.sleep(100)
    {:ok, opts}
  end

  def handle_call(:fetch, _from, state) do
    Process.sleep(250)
    {:reply, state.value, state}
  end

  def handle_cast({:enqueue, item}, state) do
    :timer.sleep(50)
    {:noreply, [item | state.queue]}
  end

  def handle_info(:tick, state) do
    sleep(10)
    {:noreply, state}
  end
end
