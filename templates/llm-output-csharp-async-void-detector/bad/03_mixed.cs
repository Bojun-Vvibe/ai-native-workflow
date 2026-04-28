using System;
using System.Threading.Tasks;

public class Mixed
{
    // BAD: parameter list does not match (object, EventArgs).
    protected override async void OnTick(TimeSpan delta)
    {
        await Task.Delay(10);
    }

    // BAD: single arg, not an event handler shape.
    internal async void Notify(string topic)
    {
        await Task.CompletedTask;
    }
}
