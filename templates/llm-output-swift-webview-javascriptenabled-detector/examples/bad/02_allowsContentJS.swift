import WebKit

func makePrefs() -> WKWebpagePreferences {
    let prefs = WKWebpagePreferences()
    prefs.allowsContentJavaScript = true
    return prefs
}
