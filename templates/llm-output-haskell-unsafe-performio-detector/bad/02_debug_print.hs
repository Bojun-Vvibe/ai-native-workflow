module BadDebug where

import System.IO.Unsafe (unsafePerformIO)

debugLog :: String -> a -> a
debugLog msg x = unsafePerformIO (putStrLn msg) `seq` x

double :: Int -> Int
double n = debugLog ("doubling " ++ show n) (n * 2)
