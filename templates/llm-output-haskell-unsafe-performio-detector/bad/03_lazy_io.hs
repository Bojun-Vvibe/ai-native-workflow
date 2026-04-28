module BadInterleave where

import System.IO
import System.IO.Unsafe (unsafeInterleaveIO)

lazyLines :: Handle -> IO [String]
lazyLines h = do
    eof <- hIsEOF h
    if eof
        then return []
        else do
            l  <- hGetLine h
            ls <- unsafeInterleaveIO (lazyLines h)
            return (l : ls)
