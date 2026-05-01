using System;

namespace SafeApp.E;

public class Strings
{
    // Construction inside string literals (regular and verbatim) MUST NOT
    // be flagged. The C#-aware stripper blanks out string contents.
    public string A => "var doc = new XmlDocument(); doc.Load(x);";
    public string B => @"var r = XmlReader.Create(x);";
    public string C => "// XmlDocument.Load is dangerous when not configured";
    public string D => "verbatim with embedded \"\" quote: new XmlTextReader(s)";
}
