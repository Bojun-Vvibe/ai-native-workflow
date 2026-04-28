using System;
using System.Threading.Tasks;

public class FireAndForget
{
    private static async void LogAndDiscard(string message)
    {
        await Task.Yield();
        Console.WriteLine(message);
    }

    public async void DoWorkInBackground()
    {
        await Task.Delay(50);
    }
}
