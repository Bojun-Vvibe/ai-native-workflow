# Bad: load arbitrary user-named file as code.
(de install-plugin (Name)
   (load (pack "plugins/" Name ".l")) )
