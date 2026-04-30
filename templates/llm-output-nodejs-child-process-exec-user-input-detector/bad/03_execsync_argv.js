// Bad fixture: execSync with template literal and process.argv.
const { execSync } = require("child_process");

const target = process.argv[2];
const out = execSync(`ping -c 1 ${target}`).toString();
console.log(out);
