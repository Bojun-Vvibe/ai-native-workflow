// config/server.js - app.keys hardcoded to placeholder list
module.exports = ({ env }) => ({
  host: env('HOST', '0.0.0.0'),
  port: env.int('PORT', 1337),
  app: {
    keys: ['toBeModified1', 'toBeModified2'],
  },
});
