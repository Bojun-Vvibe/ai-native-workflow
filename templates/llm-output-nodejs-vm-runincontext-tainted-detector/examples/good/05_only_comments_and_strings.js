// Mention the vm API only in comments and string literals.
const vm = require('vm');

const docs = "Don't call vm.runInNewContext(userCode) on user input.";

// vm.runInThisContext(snippet);  // <- bad pattern, but in a comment

console.log(docs, typeof vm);
