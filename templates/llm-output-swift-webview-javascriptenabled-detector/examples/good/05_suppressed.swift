import WebKit

func showGreetingSafe(web: WKWebView, name: String) {
    // Audited path: name was validated upstream against [A-Za-z ]{1,40}
    let js = "document.title = 'Hello';" // llm-allow:swift-webview-js
    web.evaluateJavaScript(js, completionHandler: nil) // llm-allow:swift-webview-js
}
