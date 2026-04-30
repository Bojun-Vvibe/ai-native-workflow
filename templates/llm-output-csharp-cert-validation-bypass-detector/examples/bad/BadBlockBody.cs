using System.Net.Http;

public class BadBlockBody
{
    public HttpClient Build()
    {
        var handler = new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback = (m, c, ch, e) => { return true; }
        };
        return new HttpClient(handler);
    }
}
