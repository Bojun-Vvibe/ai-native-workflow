# Bad: vm.runInThisContext on a tainted string
vm = require "vm"
src = process.argv[2]
vm.runInThisContext src
