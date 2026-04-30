// Bad: classic axios escape hatch.
const axios = require('axios');
const https = require('https');

const client = axios.create({
  baseURL: 'https://internal.example.test',
  httpsAgent: new https.Agent({ rejectUnauthorized: false }),
});

module.exports = client;
