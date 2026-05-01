def userInput = System.console().readLine()
def out = "tar -xzf ${userInput}".execute().text
println out
