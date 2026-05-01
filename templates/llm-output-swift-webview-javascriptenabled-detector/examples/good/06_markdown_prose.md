# Notes (markdown prose only)

The setting `javaScriptEnabled = true` is dangerous when the page is
attacker-controlled. The class `UIWebView` should not be used in new
code. The method `evaluateJavaScript` should never receive a built
string. The method `loadHTMLString` should only be called with a static
literal HTML body.

(No fenced code block here, so the detector should ignore everything above.)
