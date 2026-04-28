using System;
using System.Threading.Tasks;

public class GoodTaskReturns
{
    // OK: returns Task, not void.
    public async Task ProcessAsync(int orderId)
    {
        await Task.Delay(100);
    }

    public async Task<int> ComputeAsync()
    {
        await Task.Yield();
        return 42;
    }

    // Sync void is fine — the issue is specifically `async void`.
    public void Log(string message)
    {
        Console.WriteLine(message);
    }

    /* This comment mentions async void Foo(int x) but should not flag. */
    // Another mention: async void Bar(string s)
}
