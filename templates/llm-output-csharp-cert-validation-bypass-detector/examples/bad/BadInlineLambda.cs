using System.Net.Http;

public class BadInlineLambda
{
    public HttpClient Build()
    {
        var handler = new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback = (m, c, ch, e) => true
        };
        return new HttpClient(handler);
    }
}
