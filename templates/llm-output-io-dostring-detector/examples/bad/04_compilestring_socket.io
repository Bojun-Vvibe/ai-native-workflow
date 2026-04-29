// Pre-compiles attacker-controlled source into a callable block.
src := Socket recvAll
block := Object compileString(src)
block call
