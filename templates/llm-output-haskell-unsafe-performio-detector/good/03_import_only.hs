module GoodImportNoUse where

-- Importing the symbol does not constitute a "use site". The detector
-- skips import lines, so this file should produce zero findings even
-- though `unsafePerformIO` is named in the import list.

import System.IO.Unsafe (unsafePerformIO)

addOne :: Int -> Int
addOne = (+ 1)

twice :: (a -> a) -> a -> a
twice f = f . f
