import process from 'node:process';
import { pathToFileURL } from 'node:url';

const [, , endpoint] = process.argv;
if (!endpoint) {
  process.stdout.write(JSON.stringify({ ok: false, error: 'Missing endpoint' }));
  process.exit(2);
}

let input = '';
for await (const chunk of process.stdin) input += chunk;

try {
  const payload = JSON.parse(input);
  let fetchImpl = globalThis.fetch;
  let transport = 'node-built-in-fetch';
  if (process.env.SILLYTAVERN_NODE_FETCH) {
    const nodeFetchModule = await import(pathToFileURL(process.env.SILLYTAVERN_NODE_FETCH).href);
    fetchImpl = nodeFetchModule.default;
    transport = 'sillytavern-node-fetch';
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180_000);
  const response = await fetchImpl(endpoint, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.SILICONFLOW_API_KEY || ''}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    signal: controller.signal,
  });
  clearTimeout(timeout);
  const body = await response.text();
  process.stdout.write(JSON.stringify({
    ok: response.ok,
    status: response.status,
    transport,
    headers: {
      'content-type': response.headers.get('content-type') || '',
      'x-request-id': response.headers.get('x-request-id') || '',
      'x-siliconcloud-trace-id': response.headers.get('x-siliconcloud-trace-id') || '',
    },
    body,
  }));
  process.exit(response.ok ? 0 : 1);
} catch (error) {
  process.stdout.write(JSON.stringify({
    ok: false,
    status: 0,
    error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
    cause: error instanceof Error && error.cause ? String(error.cause) : '',
    stack: error instanceof Error ? error.stack || '' : '',
  }));
  process.exit(2);
}