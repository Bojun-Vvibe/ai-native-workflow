module BadConfig where

import System.IO.Unsafe (unsafePerformIO)

{-# NOINLINE configPath #-}
configPath :: FilePath
configPath = unsafePerformIO $ do
    -- LLM "fix": just read the env var here, pretend it's pure.
    return "/tmp/config.json"
