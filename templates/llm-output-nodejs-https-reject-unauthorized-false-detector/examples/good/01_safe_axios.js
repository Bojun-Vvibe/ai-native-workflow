// Good: explicit-true verification, the only safe shape.
const https = require('https');
const axios = require('axios');

const client = axios.create({
  baseURL: 'https://internal.example.test',
  httpsAgent: new https.Agent({ rejectUnauthorized: true, ca: process.env.CA_BUNDLE }),
});

module.exports = client;
