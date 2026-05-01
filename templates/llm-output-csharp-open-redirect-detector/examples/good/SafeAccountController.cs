// Good case 2: framework mitigations are present in this file —
// LocalRedirect / IsLocalUrl reject absolute and scheme-bearing URLs,
// so the detector treats anything in this file as opted-in.
// ASP.NET Core MVC controller

public class SafeAccountController : ControllerBase
{
    private readonly IUrlHelper Url;

    public IActionResult Login(string returnUrl)
    {
        if (!Url.IsLocalUrl(returnUrl))
        {
            return Redirect("/");
        }
        return LocalRedirect(returnUrl);
    }

    public IActionResult AfterLogout(string returnUrl)
    {
        return LocalRedirectPermanent(returnUrl);
    }

    public IActionResult Bounce(string nextUrl)
    {
        return new LocalRedirectResult(nextUrl);
    }
}
