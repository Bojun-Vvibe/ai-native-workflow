# Pull a script body off the network and feed it straight to the parser.
using Downloads
url = "https://example.invalid/setup.jl"
include(download(url))
