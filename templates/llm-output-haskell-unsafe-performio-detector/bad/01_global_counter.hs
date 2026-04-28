module BadCounter where

import Data.IORef
import System.IO.Unsafe (unsafePerformIO)

{-# NOINLINE counter #-}
counter :: IORef Int
counter = unsafePerformIO (newIORef 0)

bump :: Int
bump = unsafePerformIO $ do
    modifyIORef' counter (+1)
    readIORef counter
