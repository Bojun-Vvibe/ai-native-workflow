// Good case 3: suppressions and string-literal sinks.
// ASP.NET Core MVC controller

public class CommentsController : ControllerBase
{
    public IActionResult LegacyDocs()
    {
        // Triple-reviewed: target is a constant pulled from a static map,
        // not a request-bound value. The // redirect-ok marker silences
        // the detector for this single line.
        var target = LegacyMap["root"];
        return Redirect(target); // redirect-ok
    }

    public IActionResult Demo()
    {
        // The string "model.Url" appears here only as a literal — the
        // string-and-comment stripper masks it before pattern matching.
        return Redirect("/docs?note=model.Url+is+just+text");
    }

    private static readonly System.Collections.Generic.Dictionary<string, string> LegacyMap
        = new() { ["root"] = "/legacy/root" };
}
