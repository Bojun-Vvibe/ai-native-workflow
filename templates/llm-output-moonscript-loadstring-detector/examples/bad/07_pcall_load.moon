-- Bad: pcall around load — still a sink, still flagged
expr = arg[1]
fn = load(expr)
fn! if fn
