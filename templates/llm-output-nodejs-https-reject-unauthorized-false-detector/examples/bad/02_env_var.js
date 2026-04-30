// Bad: env-var nuke. Disables verification for the entire process.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

const https = require('https');
https.get('https://example.test/data', (res) => {
  res.on('data', () => {});
});
