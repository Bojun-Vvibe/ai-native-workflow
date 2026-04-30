// Bad: numeric-literal form of the env var, plus an inline literal-0 form.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = 0;

const opts = {
  host: 'cache.example.test',
  port: 6443,
  rejectUnauthorized: 0,
};

require('https').request(opts).end();
