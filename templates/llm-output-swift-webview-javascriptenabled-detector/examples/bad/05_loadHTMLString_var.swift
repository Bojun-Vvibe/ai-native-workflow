import WebKit

func renderServerHtml(web: WKWebView, body: String) {
    web.loadHTMLString(body, baseURL: nil)
}
