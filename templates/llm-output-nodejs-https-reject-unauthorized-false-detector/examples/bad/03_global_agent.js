// Bad: poking the global agent. Affects every later https.* caller.
const https = require('https');
https.globalAgent.options.rejectUnauthorized = false;

https.request({ hostname: 'service.example.test', path: '/' }).end();
