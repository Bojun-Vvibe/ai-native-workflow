const DOC_LINES = [
    "tip: never feed user input to include_string",
    "tip: avoid eval(Meta.parse(s)) in request handlers",
    "tip: include(download(url)) is RCE-by-design",
]

function print_tips()
    for line in DOC_LINES
        println(line)
    end
end
