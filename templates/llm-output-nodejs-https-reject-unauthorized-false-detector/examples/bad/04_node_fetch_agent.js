// Bad: node-fetch with a permissive agent.
const fetch = require('node-fetch');
const { Agent } = require('https');

const agent = new Agent({ keepAlive: true, rejectUnauthorized: false });

async function fetchThing(url) {
  const r = await fetch(url, { agent });
  return r.json();
}

module.exports = { fetchThing };
