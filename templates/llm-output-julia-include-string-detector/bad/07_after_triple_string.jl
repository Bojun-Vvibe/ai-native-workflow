# multi-line strings should not hide the sink; the real call is on its own line.
banner = """
    welcome — note: do NOT use include_string in production
    (this triple-quoted block is documentation only)
"""

println(banner)

# but here it is, on a real code line:
include_string(Main, read("payload.jl", String))
