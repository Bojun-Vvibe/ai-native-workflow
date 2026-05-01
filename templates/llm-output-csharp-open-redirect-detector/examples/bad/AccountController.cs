// Bad case 1: classic returnUrl reflection
using System.Web.Mvc;

public class AccountController : Controller
{
    public ActionResult Login(string returnUrl)
    {
        // attacker controls returnUrl=https://evil.example/phish
        return Redirect(returnUrl);
    }

    public ActionResult AfterLogout(string returnUrl)
    {
        return RedirectPermanent(returnUrl);
    }
}
