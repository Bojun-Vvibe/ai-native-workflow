// Good: deliberate-and-reviewed test fixture, suppressed via the audit comment.
const tls = require('tls');

// We trust this private CA pinned via `ca:` below; the disabled-verify
// is intentional inside the integration test harness only.
const sock = tls.connect({
  host: 'fixtures.test.local',
  port: 8443,
  ca: require('fs').readFileSync('test/ca.pem'),
  rejectUnauthorized: false, // tls-noverify-ok — pinned-CA test fixture
}, () => sock.end());
