using System.Net;

public class BadMultiline
{
    public void Init()
    {
        ServicePointManager.ServerCertificateValidationCallback = (s, c, ch, e) =>
            true;
    }
}
