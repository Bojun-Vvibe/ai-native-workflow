// Bad: tls.connect with verification off. Common in "fix the cert error" PRs.
const tls = require('tls');

const socket = tls.connect({
  host: 'mq.example.test',
  port: 8883,
  rejectUnauthorized: false,
}, () => {
  socket.write('PING\n');
});
