using System;
using System.Threading.Tasks;
using System.Windows;

public class GoodHandlers
{
    // OK: classic event handler signature.
    private async void Button_Click(object sender, EventArgs e)
    {
        await Task.Delay(10);
    }

    // OK: derived EventArgs is still an event handler.
    public async void OnRouted(object sender, RoutedEventArgs e)
    {
        await Task.Yield();
    }
}
