public class GoodLiteralOnly {
    // Example string in a comment that mentions SAXParserFactory.newInstance() but does not call it.
    public String describe() {
        // The token below is inside a string literal so the line stripper blanks it out.
        return "constructed via SAXParserFactory.newInstance() in legacy code";
    }
}
