# Service config (clean)

```xml
<config>
  <server>
    <host>0.0.0.0</host>
    <port>8080</port>
  </server>
</config>
```

HTML with void elements (no close needed) and a comment:

```html
<div>
  <img src="x.png"/>
  <br>
  <hr>
  <!-- a comment with <fake-tag> inside that must be ignored -->
  <p>ok</p>
</div>
```

XML with declaration, CDATA, and a numeric comparison-looking text
that must NOT be parsed as a tag:

```xml
<?xml version="1.0"?>
<root>
  <expr>x &lt; 3 and y &gt; 2</expr>
  <code><![CDATA[ if (a < b) { return 1; } ]]></code>
</root>
```
