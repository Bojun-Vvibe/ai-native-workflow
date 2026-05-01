import WebKit

func loadStaticPage(web: WKWebView) {
    web.loadHTMLString("<h1>Welcome</h1>", baseURL: nil)
}
