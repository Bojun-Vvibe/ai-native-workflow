-- good/02_in_comment.hs — the dangerous form lives only in comments
-- (line comment AND block comment). Both are stripped before
-- matching.
module Good02 where

-- Don't write code like: eval userInput
{- Or this:
   interpret expr (as :: IO ())
   runStmt s
-}
safe :: Int
safe = 1
