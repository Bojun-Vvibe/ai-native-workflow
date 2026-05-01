import WebKit

func evalConstantOnly(web: WKWebView) {
    // A pure literal is allowed — no untrusted-input shape.
    web.evaluateJavaScript("document.body.style.zoom = 1.2;", completionHandler: nil)
}
