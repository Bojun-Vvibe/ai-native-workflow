# Good fixture: same intents as bad.R, expressed without eval(parse(text=...)).

# 1: dynamic variable -> use a list (the idiomatic R answer)
models <- list()
for (i in 1:5) {
  models[[paste0("model_", i)]] <- lm(y ~ x, data = df)
}

# 2: dynamic formula -> as.formula() then standard call
build_and_run <- function(col) {
  f <- as.formula(paste0("y ~ ", col))
  summary(lm(f, data = df))
}

# 3: dynamic column reference -> [[ ]] indexing, no parsing
get_value <- function(name) {
  df[[name]]
}

# 4: parse(file = ...) is a legitimate "source another script" pattern
#    — the detector must NOT flag this.
exprs <- parse(file = "helpers.R")
eval(exprs)

# 5: evaluating an already-quoted expression (normal metaprogramming)
e <- quote(x + 1)
eval(e)

# 6: bquote / substitute for code generation
template <- bquote(z <- .(a) + .(b), list(a = 1, b = 2))
eval(template)

# 7: a comment that mentions eval(parse(text = ...)) must not trigger:
# avoid eval(parse(text = ...)) — it's an injection sink

# 8: a string literal that mentions it must not trigger either:
warning_message <- "do not use eval(parse(text = x)) in production"

# 9: an audited internal use can be suppressed inline:
internal_eval <- function(s) {
  eval(parse(text = s)) # eval-parse-ok: knitr chunk option parser, internal-only
}
