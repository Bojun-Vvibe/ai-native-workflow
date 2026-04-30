using System.Net.Http;

public class GoodPinning
{
    private static readonly string ExpectedThumbprint = "ABCDEF0123456789";

    public HttpClient Build()
    {
        var handler = new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback = (msg, cert, chain, errors) =>
            {
                return cert != null && cert.GetCertHashString() == ExpectedThumbprint;
            }
        };
        return new HttpClient(handler);
    }
}
