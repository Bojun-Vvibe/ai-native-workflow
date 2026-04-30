using System.Net.Http;

public class BadDangerousValidator
{
    public HttpClient Build()
    {
        var handler = new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback =
                HttpClientHandler.DangerousAcceptAnyServerCertificateValidator
        };
        return new HttpClient(handler);
    }
}
