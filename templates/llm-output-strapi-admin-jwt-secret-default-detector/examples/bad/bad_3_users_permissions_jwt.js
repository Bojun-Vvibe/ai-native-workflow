// config/plugins.js - users-permissions with literal jwtSecret
module.exports = ({ env }) => ({
  'users-permissions': {
    config: {
      jwt: {
        expiresIn: '7d',
      },
      jwtSecret: 'changeme',
    },
  },
});
