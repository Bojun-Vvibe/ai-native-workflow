# Service config

The model produced this XML — but the tags don't balance:

```xml
<config>
  <server>
    <host>0.0.0.0</host>
    <port>8080</port>
  <!-- forgot to close <server> -->
</config>
```

Crossed nesting in an HTML snippet:

```html
<div>
  <p>hello <strong>world</p></strong>
</div>
```

Stray closer with no opener:

```xml
<root>
  <child/>
</root>
</extra>
```
