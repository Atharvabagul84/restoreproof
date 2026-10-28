// Fixed local endpoints only. Request, cookies and CA arrive on stdin, never argv.
const http = require('node:http');
const https = require('node:https');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const targets = { app: [https, 3443], mail: [http, 8025], auth: [http, 9999], rest: [http, 3000] };
if (!Object.hasOwn(targets, input.target) || !/^\/(?!\/)[^\r\n]*$/.test(input.path)) process.exit(3);
const [transport, port] = targets[input.target];
const data = input.body === undefined ? null : JSON.stringify(input.body);
const headers = { ...input.headers };
if (data) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = Buffer.byteLength(data); }
const request = transport.request({ hostname: '127.0.0.1', port, path: input.path,
  method: input.method || 'GET', headers, ca: input.ca, timeout: 10000 }, response => {
  const chunks = []; let size = 0;
  response.on('data', chunk => { size += chunk.length; if (size > 524288) request.destroy(); else chunks.push(chunk); });
  response.on('end', () => {
    const text = Buffer.concat(chunks).toString('utf8'); let body;
    try { body = JSON.parse(text); } catch { body = text; }
    process.stdout.write(JSON.stringify({ status: response.statusCode, cookies: response.headers['set-cookie'] || [], body }));
  });
});
request.on('timeout', () => request.destroy());
request.on('error', () => { process.stderr.write('Local request failed.'); process.exitCode = 2; });
request.end(data);
