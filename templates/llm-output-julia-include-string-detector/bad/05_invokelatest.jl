function reload_world(src::String)
    # invokelatest is sometimes used to side-step world-age, still RCE.
    Base.invokelatest(eval, Meta.parse(src))
end
