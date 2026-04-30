using System.Net.Http;

public class GoodSuppressedTest
{
    // Test-only fixture, audited; never compiled into production binary.
    public HttpClient BuildForUnitTest()
    {
        var handler = new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback = (m, c, ch, e) => true // cert-validation-ok
        };
        return new HttpClient(handler);
    }
}
