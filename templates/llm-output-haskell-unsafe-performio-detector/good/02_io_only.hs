module GoodIO where

import Data.IORef

-- Plain IO is fine. We don't escape to a pure context, so no unsafe
-- needed. The detector should not flag anything in this file.

makeCounter :: IO (IO Int)
makeCounter = do
    ref <- newIORef (0 :: Int)
    return $ do
        modifyIORef' ref (+ 1)
        readIORef ref

main :: IO ()
main = do
    bump <- makeCounter
    n1 <- bump
    n2 <- bump
    print (n1, n2)
