' bad: looped Execute over each line of a file
Dim lines, i
lines = SplitFile("rules.txt")
For i = 0 To UBound(lines)
    Execute lines(i)
Next
