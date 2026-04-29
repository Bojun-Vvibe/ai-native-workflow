# Bad: load is sometimes used as a poor man's require with dynamic name.
(de boot (Mod)
   (load Mod)
   (msg "loaded" Mod) )
