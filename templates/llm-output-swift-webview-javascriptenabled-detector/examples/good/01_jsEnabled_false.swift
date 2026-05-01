import WebKit

// Explicitly disabled — the safe configuration for static help pages.
func makeReadOnlyWeb() -> WKWebView {
    let cfg = WKWebViewConfiguration()
    cfg.preferences.javaScriptEnabled = false
    return WKWebView(frame: .zero, configuration: cfg)
}
