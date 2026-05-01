// Bad case 2: pulling the URL from query/form/header dictionaries
// ASP.NET Core MVC controller

public class JumpController : ControllerBase
{
    public IActionResult FromQuery()
    {
        var target = Request.Query["next"];
        return Redirect(target);
    }

    public IActionResult FromForm()
    {
        return Redirect(Request.Form["redirectUrl"]);
    }

    public IActionResult FromHeader()
    {
        return Redirect(Request.Headers["X-Return-To"]);
    }

    public void Legacy()
    {
        Response.Redirect(Request.Query["redirect_uri"]);
    }

    public IActionResult FromCookie()
    {
        return Redirect(Request.Cookies["return_to"]);
    }
}
