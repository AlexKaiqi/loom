// Pi owns model/auth metadata. This offline catalog advertises only the setup
// path we can reproduce: API-key auth, concrete endpoint, no discarded headers.
import { builtinProviders, getBuiltinModels } from '@earendil-works/pi-ai/providers/all';
import { supportsAPI } from './pi.mjs';

function concreteEndpoint(value) {
  if (typeof value !== 'string' || !value || /[{}]/.test(value)) return false;
  try {
    const endpoint = new URL(value);
    return ['http:', 'https:'].includes(endpoint.protocol) && endpoint.hostname &&
      !endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash;
  } catch { return false; }
}
function directModels(provider) {
  if (!provider.auth?.apiKey || Object.keys(provider.headers ?? {}).length) return [];
  return getBuiltinModels(provider.id).filter(model => supportsAPI(model.api) &&
    concreteEndpoint(model.baseUrl) && !Object.keys(model.headers ?? {}).length);
}
function unavailable() {
  process.stderr.write('Model is not available for API-key setup in the installed Pi catalog; use an explicit custom model and host configuration.\n');
  process.exit(1);
}
const catalog = new Map(builtinProviders().map(provider => [provider.id, directModels(provider)])
  .filter(([, models]) => models.length));
const [provider, id] = process.argv.slice(2);
let value;
if (!provider) value = [...catalog.keys()];
else {
  const models = catalog.get(provider);
  if (!models) unavailable();
  if (!id) value = models.map(({ id, name, api }) => ({ id, name, api }));
  else {
    const model = models.find(model => model.id === id);
    if (!model) unavailable();
    const { baseUrl, headers: _headers, ...definition } = model;
    value = { endpoint: baseUrl, definition };
  }
}
process.stdout.write(JSON.stringify(value) + '\n');
