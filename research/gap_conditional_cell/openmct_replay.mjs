// Opt-in original-class Open MCT source replay at a pinned upstream commit.
// The three upstream source files are loaded without rewriting them. Only
// unrelated import dependencies and setInterval timing are controlled here.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

const PIN = 'e09bfaf47856b2b7ae2ea74334800b26fd27a41e';
const API_SHA = '95c39cfe100fb27724927976a1cc50a0576becb28e9f70e58c159803bc827802';
const SOURCE_FILES = {
  api: ['src/api/telemetry/TelemetryAPI.js', API_SHA],
  utils: ['src/api/objects/object-utils.js', 'b9c36ed40e67c487ffa2bb4873f036b7ae023ce7ca49bf7dc71bcf2dd2211b09'],
  provider: ['example/generator/StateGeneratorProvider.js', 'cc1f7d0a6b9f15d91d0996ee7225672b2d1f6599950447af71cc741c7b919f0c']
};

const checkout = resolve(process.argv[2] || '.');
const commit = execFileSync('git', ['-C', checkout, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
if (commit !== PIN) throw new Error('OPENMCT_SOURCE_COMMIT_MISMATCH');

const texts = {};
for (const [label, [path, expected]] of Object.entries(SOURCE_FILES)) {
  const bytes = readFileSync(resolve(checkout, path));
  const actual = createHash('sha256').update(bytes).digest('hex');
  if (actual !== expected) throw new Error(`OPENMCT_SOURCE_DIGEST_MISMATCH:${label}`);
  texts[label] = bytes.toString('utf8');
}

const intervals = new Map();
let nextId = 1;
let now = 2000;
const context = vm.createContext({
  console,
  setInterval(callback) { const id = nextId++; intervals.set(id, callback); return id; },
  clearInterval(id) { intervals.delete(id); },
  getFixtureTime() { return now; },
});

const utils = new vm.SourceTextModule(texts.utils, { context, identifier: 'object-utils' });
const provider = new vm.SourceTextModule(texts.provider, { context, identifier: 'StateGeneratorProvider' });
const api = new vm.SourceTextModule(texts.api, { context, identifier: 'TelemetryAPI' });
const stubs = new Map();
await api.link(async (specifier) => {
  if (specifier === 'objectUtils') return utils;
  if (!stubs.has(specifier)) {
    stubs.set(specifier, new vm.SyntheticModule(['default'], function () {
      this.setExport('default', class UnusedDependency {});
    }, { context, identifier: `stub:${specifier}` }));
  }
  return stubs.get(specifier);
});
await provider.link(async () => { throw new Error('Unexpected provider import'); });
await api.evaluate();
await provider.evaluate();
context.TelemetryAPI = api.namespace.default;
context.StateGeneratorProvider = provider.namespace.default;

vm.runInContext(`
  globalThis.optionsOff = {filters:{state:{equals:[' +0000.0E-0 ']}}};
  globalThis.optionsOn = {filters:{state:{equals:['  00000001.e0000']}}};
  globalThis.receivedA = [];
  globalThis.receivedB = [];
  globalThis.receivedEqual = [];
  globalThis.receivedControl = [];
  globalThis.providerCalls = 0;
  const openmct = {time:{now:getFixtureTime,getTimeSystem:()=>({key:'utc'})}};
  const sourceProvider = new StateGeneratorProvider(openmct);
  const realSubscribe = sourceProvider.subscribe.bind(sourceProvider);
  sourceProvider.subscribe = (...arguments_) => {
    globalThis.providerCalls += 1;
    return realSubscribe(...arguments_);
  };
  globalThis.telemetry = new TelemetryAPI(openmct);
  telemetry.addProvider(sourceProvider);
  globalThis.domain = {type:'example.state-generator',name:'test',identifier:{namespace:'demo',key:'state'},telemetry:{duration:1}};
  telemetry.subscribe(domain, datum=>receivedA.push(Number(datum.value)), optionsOff);
  telemetry.subscribe(domain, datum=>receivedB.push(Number(datum.value)), optionsOn);
  const callsBeforeEqual = providerCalls;
  telemetry.subscribe(domain, datum=>receivedEqual.push(Number(datum.value)), optionsOff);
  globalThis.identicalOptionsReused = providerCalls === callsBeforeEqual;
  globalThis.jsonDistinct = JSON.stringify(optionsOff) !== JSON.stringify(optionsOn);
  globalThis.numericValues = [Number(optionsOff.filters.state.equals[0]),Number(optionsOn.filters.state.equals[0])];
`, context);

const callsAfterShared = context.providerCalls;
if (intervals.size !== 1) throw new Error('Unexpected non-collision in native class replay');
[...intervals.values()][0](); // Actual upstream provider and subscribed API run at state 0.

now = 3000;
vm.runInContext(`
  const distinctDomain = {...domain,identifier:{namespace:'demo',key:'state-control'}};
  telemetry.subscribe(distinctDomain, datum=>receivedControl.push(Number(datum.value)), optionsOn);
`, context);
if (intervals.size !== 2) throw new Error('Independent-domain positive control unavailable');
[...intervals.values()][1](); // Actual upstream provider runs at state 1.

const result = {
  schema: 'mathgraph/openmct-original-class-replay-v1',
  source_commit: commit,
  telemetry_api_sha256: API_SHA,
  options_json_distinct: context.jsonDistinct,
  alias_numeric_values: Array.from(context.numericValues),
  shared_provider_subscriptions: callsAfterShared,
  shared_received: [Array.from(context.receivedA), Array.from(context.receivedB)],
  independent_control_received: Array.from(context.receivedControl),
  identical_options_reused: context.identicalOptionsReused,
  boundary: 'Original API/provider/util source; unrelated imports and timer environment stubbed. Not complete app, Karma suite or owner repair authorization.'
};
console.log(JSON.stringify(result));
