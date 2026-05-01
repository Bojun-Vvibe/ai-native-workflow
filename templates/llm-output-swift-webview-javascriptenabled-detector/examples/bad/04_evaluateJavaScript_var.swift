import WebKit

extension WKWebView {
    func showGreeting(name: String) {
        // String interpolation directly into the JS body — XSS waiting to happen.
        let js = "document.title = 'Hello, \(name)';"
        self.evaluateJavaScript(js, completionHandler: nil)
    }
}
