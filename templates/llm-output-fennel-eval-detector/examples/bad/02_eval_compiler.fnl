;; bad: compiler-scope mutation from a literal
(eval-compiler (set _G.x 1))
