module GoodPure where

-- Pure code: no unsafe escape hatches. The string literal mentions the
-- name "unsafePerformIO" and a comment says it too, but neither should
-- be flagged.
--
-- Reminder: never reach for unsafePerformIO to "just log something".

note :: String
note = "If you find yourself typing unsafePerformIO, stop."

square :: Int -> Int
square x = x * x

sumSquares :: [Int] -> Int
sumSquares = foldr (\x acc -> square x + acc) 0
