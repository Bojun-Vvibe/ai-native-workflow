using System.Net.Http;
using System.Net.Security;

public class GoodRealCallback
{
    public HttpClient Build()
    {
        var handler = new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback = (msg, cert, chain, errors) =>
            {
                if (errors == SslPolicyErrors.None) return true;
                return false;
            }
        };
        return new HttpClient(handler);
    }
}
