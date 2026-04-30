// Good: prose mention inside comments and string literals must not trigger.
//
// We used to write: rejectUnauthorized: false  ← do not do this.
// We also used to set process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0' globally.
const advice = "never set rejectUnauthorized: false in production code";
console.log(advice);
