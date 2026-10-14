import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {checkState, disciplineChecks, planningStages} from '../src/planning.ts';
import type {Check, Result, Revision} from '../src/types.ts';

const check = (rule_id: string, status: string, objects: string[] = []): Check => ({id: rule_id + objects.join('-'), rule_id, status, objects, revision_id: 'rev', rule_version: '1', evidence: '', explanation: '', inputs: {}});
const result = (): Result => ({stale: false, terrain: {status: 'pass'}, structure: {beams: []}, routing: {routes: [
  {id: 'water-sink', kind: 'water'}, {id: 'drain-sink', kind: 'drain'}, {id: 'conduit-ac', kind: 'conduit'},
]}, quantities: {items: [{}], unpriced: []}, checks: [
  check('LAYOUT', 'pass'), check('FITOUT', 'pass'), check('SLS', 'pass'),
  check('ROUTE', 'pass', ['water-sink', 'sink']), check('DRAIN', 'pass', ['drain-sink', 'sink']),
  check('ROUTE', 'fail', ['conduit-ac', 'ac']), check('ELECTRICAL', 'missing_input', ['ac']),
  check('PH-CODE', 'unsupported'),
]} as Result);
const revision = (): Revision => ({id: 'rev', status: 'accepted', model: {
  site: {survey: [{}, {}, {}]}, brief: {use: 'Studio', budget: 100}, rooms: [], equipment: [], furniture: [], fixtures: [], fire: {enabled: false}, solar: {enabled: false},
}, results: result()} as Revision);

test('route failures are assigned to the correct discipline', () => {
  const r = result();
  assert.deepEqual(disciplineChecks(r, 'plumbing').map(c => c.status), ['pass', 'pass']);
  assert.deepEqual(disciplineChecks(r, 'electrical').map(c => c.status), ['fail', 'missing_input']);
  assert.equal(checkState(disciplineChecks(r, 'plumbing')).state, 'ready');
  assert.equal(checkState(disciplineChecks(r, 'electrical')).state, 'attention');
});
test('empty, missing and unsupported-only coverage never counts as prepared', () => {
  assert.equal(checkState([]).state, 'missing');
  assert.equal(checkState([check('PV-WIND', 'unsupported')]).state, 'missing');
  assert.equal(checkState([check('SLS', 'pass'), check('BEARING', 'missing_input')]).state, 'missing');
});
test('disabled fire and optional PV do not silently pass', () => {
  const stages = planningStages(revision());
  assert.equal(stages.find(s => s.id === 'fire')?.state, 'idle');
  assert.equal(stages.find(s => s.id === 'solar')?.state, 'optional');
  assert.equal(stages.find(s => s.id === 'handoff')?.state, 'attention');
});
test('stale results cannot show ready stages or completed handoff', () => {
  const rev = revision(); rev.results.stale = true;
  const stages = planningStages(rev);
  for (const id of ['site', 'layout', 'fitout', 'structure', 'plumbing', 'electrical', 'quantities', 'handoff']) assert.equal(stages.find(s => s.id === id)?.state, 'stale');
  assert.equal(stages.find(s => s.id === 'brief')?.state, 'ready');
});
test('candidate acceptance is a separate step from computed screens', () => {
  const rev = revision(); rev.status = 'candidate';
  assert.equal(planningStages(rev).find(s => s.id === 'handoff')?.label, 'Candidate to review');
});
test('unpriced equipment prevents a complete estimate', () => {
  const rev = revision(); rev.results.quantities.unpriced = [{id: 'fire_exits', net: 1, formula: 'count'}];
  assert.equal(planningStages(rev).find(s => s.id === 'quantities')?.state, 'missing');
});
test('enabling a discipline uses its own screens and includes it in progress', () => {
  const rev = revision(); rev.model.solar.enabled = true;
  rev.results.checks.push(check('PV-ROOF', 'pass'), check('PV-BUSBAR', 'missing_input'), check('PV-WIND', 'unsupported'));
  assert.equal(disciplineChecks(rev.results, 'solar').length, 3);
  assert.equal(planningStages(rev).find(s => s.id === 'solar')?.state, 'missing');
});
