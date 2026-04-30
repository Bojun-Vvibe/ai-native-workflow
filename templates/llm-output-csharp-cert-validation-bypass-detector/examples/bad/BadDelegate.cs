using System.Net;

public class BadDelegate
{
    public void Init()
    {
        ServicePointManager.ServerCertificateValidationCallback =
            delegate(object s, System.Security.Cryptography.X509Certificates.X509Certificate c, System.Security.Cryptography.X509Certificates.X509Chain ch, System.Net.Security.SslPolicyErrors e) { return true; };
    }
}
