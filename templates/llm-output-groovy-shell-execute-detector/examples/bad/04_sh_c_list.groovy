def script = params.payload
["sh", "-c", script].execute().waitFor()
