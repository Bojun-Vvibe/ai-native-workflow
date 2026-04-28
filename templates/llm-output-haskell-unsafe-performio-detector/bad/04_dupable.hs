module BadDupable where

import System.IO.Unsafe (unsafeDupablePerformIO)
import Data.IORef

cached :: IORef (Maybe Int) -> Int -> Int
cached ref x = unsafeDupablePerformIO $ do
    m <- readIORef ref
    case m of
        Just v  -> return v
        Nothing -> do
            writeIORef ref (Just (x * x))
            return (x * x)
