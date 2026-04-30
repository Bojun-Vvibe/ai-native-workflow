using System.Net.Security;

public class BadSslStream
{
    public void Configure(SslStream s)
    {
        // Hypothetical — RemoteCertificateValidationCallback is normally
        // passed at SslStream construction; assigning a property of this
        // exact name with a trivial-true body is the pattern we catch.
        var cb = new RemoteCertificateValidationCallback((sender, cert, chain, errors) => true);
    }

    public RemoteCertificateValidationCallback Cb { get; set; } = (s, c, ch, e) => true;
}
