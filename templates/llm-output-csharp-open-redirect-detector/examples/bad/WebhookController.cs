// Bad case 3: model-bound URL + new RedirectResult
// ASP.NET Core MVC controller

public class WebhookController : ControllerBase
{
    public class CallbackDto { public string Url { get; set; } }

    public IActionResult Bounce([FromBody] CallbackDto dto)
    {
        return new RedirectResult(dto.Url);
    }

    public IActionResult Bounce2(CallbackDto model)
    {
        return Redirect(model.Url);
    }

    public IActionResult Bounce3(string nextUrl)
    {
        return RedirectPreserveMethod(nextUrl);
    }
}
