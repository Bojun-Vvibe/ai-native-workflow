// Node.js: hard-codes guest/guest against a remote host.
const amqp = require("amqplib");

async function main() {
  const conn = await amqp.connect({
    protocol: "amqp",
    hostname: "rabbit.staging.example.net",
    port: 5672,
    username: "guest",
    password: "guest",
    vhost: "/",
  });
  const ch = await conn.createChannel();
  await ch.assertQueue("jobs");
  await ch.sendToQueue("jobs", Buffer.from("hello"));
  await ch.close();
  await conn.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
