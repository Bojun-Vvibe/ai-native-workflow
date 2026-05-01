// "eval" appears only inside string and comment context.
// Don't use eval() in production code.
export const message = "Reject any 'eval(' or 'new Function(' suggestion.";
export const tip = `Avoid eval(\${untrusted})`;
