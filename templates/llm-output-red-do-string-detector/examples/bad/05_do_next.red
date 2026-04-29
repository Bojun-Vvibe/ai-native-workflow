Red [Title: "do/next loop"]

stream: read %commands.txt
while [not tail? stream] [
    set [val stream] do/next stream
]
