-- good/03_in_string.hs — the literal word `eval` appears INSIDE a
-- string literal that is being passed to printf, not as a function
-- call. String contents are blanked before matching.
module Good03 where
import Text.Printf

msg :: String -> String
msg name = printf "would eval %s but does not" name

interpretLabel :: String
interpretLabel = "interpret runStmt eval -- these are just words"
