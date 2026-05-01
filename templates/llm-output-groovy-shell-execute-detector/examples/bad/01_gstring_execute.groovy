def name = params.name
def output = "echo Hello ${name}".execute().text
println output
