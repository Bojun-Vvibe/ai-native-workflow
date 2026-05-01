// Good case 1: hard-coded literal — never tainted, no finding.
// ASP.NET Core MVC controller

public class HomeController : ControllerBase
{
    public IActionResult Index()
    {
        return Redirect("/home");
    }

    public IActionResult Health()
    {
        return Redirect("/_status/health");
    }

    public IActionResult Docs()
    {
        return new RedirectResult("/docs/index.html");
    }
}
