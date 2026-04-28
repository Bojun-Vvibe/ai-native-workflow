using System;
using System.Threading.Tasks;

public class OrderProcessor
{
    // BAD: async void on a regular method — exceptions crash the process.
    public async void ProcessOrderAsync(int orderId)
    {
        await Task.Delay(100);
        throw new InvalidOperationException("oops");
    }
}
