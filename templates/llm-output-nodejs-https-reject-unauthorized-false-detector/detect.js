#!/usr/bin/env node
/* eslint-disable */
/**
 * Detect Node.js code that disables TLS certificate verification.
 *
 * What this flags
 * ---------------
 *   - object literals containing `rejectUnauthorized: false`
 *     (https.request / https.Agent / tls.connect / axios httpsAgent /
 *     node-fetch agent, etc.)
 *   - assignments to `process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'`
 *     (or "0", or 0)
 *   - `https.globalAgent.options.rejectUnauthorized = false`
 *   - new Agent({ rejectUnauthorized: false }) shapes
 *
 * What this does NOT flag
 * -----------------------
 *   - `rejectUnauthorized: true` (the safe default)
 *   - lines marked with a trailing `// tls-noverify-ok` comment
 *   - occurrences inside `//` line comments and `/* ... *\/` blocks
 *   - occurrences inside string literals
 *
 * Finding kinds
 * -------------
 *   - tls-rejectunauthorized-false
 *   - tls-env-disable
 *   - tls-globalagent-disable
 *
 * Usage
 * -----
 *   node detect.js <file_or_dir> [...]
 *
 * Exit code 1 if any findings, 0 otherwise. Pure node stdlib.
 * Recurses directories looking for *.js, *.mjs, *.cjs, *.ts files.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const SUPPRESS = /\/\/\s*tls-noverify-ok\b/;

const RE_REJECT_FALSE = /\brejectUnauthorized\s*:\s*(?:false|0)\b/g;
const RE_ENV_DISABLE = /\bprocess\s*\.\s*env\s*\.\s*NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*(?:['"]0['"]|0)\b/g;
const RE_GLOBAL_AGENT = /\bhttps\s*\.\s*globalAgent\s*\.\s*options\s*\.\s*rejectUnauthorized\s*=\s*(?:false|0)\b/g;

const SCAN_EXTS = new Set(['.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx']);

function stripCommentsAndStrings(line, state) {
  let out = '';
  let i = 0;
  const n = line.length;
  let inStr = state.inStr; // null | "'" | '"' | '`'
  let inBlock = state.inBlock;
  while (i < n) {
    const ch = line[i];
    const nx = line[i + 1];
    if (inBlock) {
      if (ch === '*' && nx === '/') { inBlock = false; out += '  '; i += 2; continue; }
      out += ' ';
      i += 1;
      continue;
    }
    if (inStr) {
      if (ch === '\\' && i + 1 < n) { out += '  '; i += 2; continue; }
      if (ch === inStr) { out += ch; inStr = null; i += 1; continue; }
      out += ' ';
      i += 1;
      continue;
    }
    if (ch === '/' && nx === '/') { out += ' '.repeat(n - i); break; }
    if (ch === '/' && nx === '*') { inBlock = true; out += '  '; i += 2; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { inStr = ch; out += ch; i += 1; continue; }
    out += ch;
    i += 1;
  }
  state.inStr = inStr;
  state.inBlock = inBlock;
  return out;
}

function scanFile(filePath, findings) {
  let text;
  try { text = fs.readFileSync(filePath, 'utf8'); }
  catch { return; }
  const lines = text.split(/\r?\n/);
  const state = { inStr: null, inBlock: false };
  for (let li = 0; li < lines.length; li++) {
    const raw = lines[li];
    const scrubbed = stripCommentsAndStrings(raw, state);
    if (SUPPRESS.test(raw)) continue;

    let m;
    RE_REJECT_FALSE.lastIndex = 0;
    while ((m = RE_REJECT_FALSE.exec(scrubbed)) !== null) {
      findings.push({ file: filePath, line: li + 1, col: m.index + 1,
        kind: 'tls-rejectunauthorized-false', snippet: raw.trim() });
    }
    RE_ENV_DISABLE.lastIndex = 0;
    while ((m = RE_ENV_DISABLE.exec(scrubbed)) !== null) {
      findings.push({ file: filePath, line: li + 1, col: m.index + 1,
        kind: 'tls-env-disable', snippet: raw.trim() });
    }
    RE_GLOBAL_AGENT.lastIndex = 0;
    while ((m = RE_GLOBAL_AGENT.exec(scrubbed)) !== null) {
      findings.push({ file: filePath, line: li + 1, col: m.index + 1,
        kind: 'tls-globalagent-disable', snippet: raw.trim() });
    }
  }
}

function* walk(p) {
  let st;
  try { st = fs.statSync(p); } catch { return; }
  if (st.isFile()) {
    if (SCAN_EXTS.has(path.extname(p))) yield p;
    return;
  }
  if (st.isDirectory()) {
    let entries;
    try { entries = fs.readdirSync(p).sort(); } catch { return; }
    for (const e of entries) yield* walk(path.join(p, e));
  }
}

function main(argv) {
  if (argv.length < 3) {
    process.stderr.write(`usage: ${argv[1]} <file_or_dir> [...]\n`);
    return 2;
  }
  const findings = [];
  for (let i = 2; i < argv.length; i++) {
    for (const f of walk(argv[i])) scanFile(f, findings);
  }
  for (const f of findings) {
    process.stdout.write(`${f.file}:${f.line}:${f.col}: ${f.kind} \u2014 ${f.snippet}\n`);
  }
  process.stdout.write(`# ${findings.length} finding(s)\n`);
  return findings.length ? 1 : 0;
}

process.exit(main(process.argv));
