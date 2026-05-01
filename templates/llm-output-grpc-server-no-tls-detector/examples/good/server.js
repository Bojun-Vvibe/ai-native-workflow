const fs = require('fs');
const grpc = require('@grpc/grpc-js');

function startServer() {
  const server = new grpc.Server();
  const creds = grpc.ServerCredentials.createSsl(
    fs.readFileSync('ca.crt'),
    [{ private_key: fs.readFileSync('server.key'), cert_chain: fs.readFileSync('server.crt') }],
    true
  );
  server.bindAsync('0.0.0.0:50051', creds, () => server.start());
}

module.exports = { startServer };
