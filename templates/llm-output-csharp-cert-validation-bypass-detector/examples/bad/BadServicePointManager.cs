using System.Net;

public class BadServicePointManager
{
    public void Init()
    {
        ServicePointManager.ServerCertificateValidationCallback = (s, c, ch, e) => true;
    }
}
