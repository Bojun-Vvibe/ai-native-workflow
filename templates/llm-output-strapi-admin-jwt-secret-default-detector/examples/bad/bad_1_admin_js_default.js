// config/admin.js
module.exports = ({ env }) => ({
  auth: {
    secret: env('ADMIN_JWT_SECRET', 'tobemodified'),
  },
  apiToken: {
    salt: env('API_TOKEN_SALT', 'aSecretSalt'),
  },
});
