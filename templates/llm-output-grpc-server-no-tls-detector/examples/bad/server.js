const grpc = require('@grpc/grpc-js');

function startServer() {
  const server = new grpc.Server();
  server.bindAsync(
    '0.0.0.0:50051',
    grpc.ServerCredentials.createInsecure(),
    () => server.start()
  );
}

module.exports = { startServer };
