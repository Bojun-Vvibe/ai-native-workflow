// Good: similarly-spelled identifiers that must not trigger.
const config = {
  // Custom field unrelated to TLS — name collides on substring only.
  rejectAllUnauthorized: true,
  // Unrelated boolean.
  acceptUnknownClient: false,
};

module.exports = config;
