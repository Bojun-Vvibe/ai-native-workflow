# Bad fixture: 5+ instances of the eval(parse(text=...)) anti-idiom in R.

# 1: classic dynamic-variable assignment
for (i in 1:5) {
  eval(parse(text = paste0("model_", i, " <- lm(y ~ x, data = df)")))
}

# 2: dynamic formula via sprintf
build_and_run <- function(col) {
  eval(parse(text = sprintf("summary(df$%s)", col)))
}

# 3: column-name interpolation from a function arg (injection sink)
get_value <- function(name) {
  eval(parse(text = paste0("df$", name)))
}

# 4: fully qualified base::eval — still the same anti-idiom
base::eval(parse(text = "x <- 1 + 1"))

# 5: evalq form
evalq(parse(text = "y <- 2"))

# 6: str2lang variant — also flagged
run_str <- function(s) {
  eval(str2lang(s))
}

# 7: str2expression variant
run_expr <- function(s) {
  eval(str2expression(s))
}

# 8: multi-line call (still detected)
eval(
  parse(
    text = paste0("z <- ", 1, " + ", 2)
  )
)
