import type {Check, Revision, Result} from './types.ts';

export type Discipline = 'plumbing' | 'fire' | 'electrical' | 'structure' | 'solar';
export type StageId = 'site' | 'brief' | 'layout' | 'fitout' | Discipline | 'quantities' | 'handoff';
export type StageState = 'ready' | 'attention' | 'missing' | 'idle' | 'stale' | 'optional';
export type Stage = {id: StageId; title: string; detail: string; state: StageState; label: string; group: number};

export const disciplines: {id: Discipline; label: string; scope: string}[] = [
  {id: 'plumbing', label: 'Plumbing', scope: 'Water routes, clashes and gravity drain fall. Pipe sizing, hydraulics and venting are not evaluated.'},
  {id: 'fire', label: 'Fire protection', scope: 'Single-storey business and mercantile screening. Confirm occupancy before using the results; residential fire review is outside this screen.'},
  {id: 'electrical', label: 'Electrical', scope: 'Equipment loads, circuit arithmetic and conduit paths. Protection, cable sizing and voltage drop are not evaluated.'},
  {id: 'structure', label: 'Structure', scope: 'Independent roof beams and centered bearing. Whole-building stability, wind, seismic and connections are not evaluated.'},
  {id: 'solar', label: 'Solar PV', scope: 'Array fit, added roof load and selected electrical screens. Wind uplift, attachments and utility approval remain outside this review.'},
];

/** ROUTE checks serve two disciplines. Match route identities, never the generic rule alone. */
export function disciplineChecks(result: Result, discipline: Discipline): Check[] {
  const routes = new Set(result.routing.routes.filter(route =>
    discipline === 'electrical' ? route.kind === 'conduit' : ['water', 'drain'].includes(route.kind)
  ).map(route => route.id));
  return result.checks.filter(check => {
    if (discipline === 'fire') return check.rule_id.startsWith('FIRE-');
    if (discipline === 'solar') return check.rule_id.startsWith('PV-');
    if (discipline === 'structure') return ['SLS', 'ELASTIC', 'BEARING'].includes(check.rule_id);
    if (discipline === 'electrical' && check.rule_id === 'ELECTRICAL') return true;
    return ['ROUTE', 'DRAIN'].includes(check.rule_id) && check.objects.some(id => routes.has(id));
  });
}

export function checkState(checks: Check[]): Pick<Stage, 'state' | 'label'> {
  const failures = checks.filter(c => c.status === 'fail').length;
  const missing = checks.filter(c => c.status === 'missing_input').length;
  if (failures) return {state: 'attention', label: `${failures} finding${failures === 1 ? '' : 's'}`};
  if (missing) return {state: 'missing', label: `${missing} missing input${missing === 1 ? '' : 's'}`};
  if (!checks.some(c => c.status === 'pass')) return {state: 'missing', label: 'Not assessed'};
  return {state: 'ready', label: 'Screens calculated'};
}

export function planningStages(revision: Revision): Stage[] {
  const {model: b, results: r} = revision;
  const screened = (id: StageId, title: string, detail: string, group: number, checks: Check[]): Stage =>
    ({id, title, detail, group, ...checkState(checks), ...(r.stale ? {state: 'stale' as const, label: 'Recompute'} : {})});
  const stages: Stage[] = [
    {id: 'site', title: 'Site & survey', detail: `${b.site.survey.length} survey points · boundary & levels`, group: 0,
      state: r.stale ? 'stale' : b.site.survey.length >= 3 && r.terrain.status === 'pass' ? 'ready' : 'missing', label: r.stale ? 'Recompute' : b.site.survey.length >= 3 && r.terrain.status === 'pass' ? 'Inputs available' : 'Review site data'},
    {id: 'brief', title: 'Project brief', detail: `${b.rooms.length} spaces · use, budget & constraints`, group: 0,
      state: b.brief.use && b.brief.budget > 0 ? 'ready' : 'missing', label: b.brief.use && b.brief.budget > 0 ? 'Inputs available' : 'Add requirements'},
    screened('layout', 'Rooms & circulation', 'Edit the plan or generate alternatives', 1, r.checks.filter(c => c.rule_id === 'LAYOUT')),
    screened('fitout', 'Furniture & access', `${b.furniture.length} placements · clearances`, 1, r.checks.filter(c => c.rule_id === 'FITOUT')),
    screened('structure', 'Structure', `${r.structure.beams.length} roof beams · bearing`, 2, disciplineChecks(r, 'structure')),
    screened('electrical', 'Electrical', `${b.equipment.length} loads · circuits & conduit`, 2, disciplineChecks(r, 'electrical')),
    screened('plumbing', 'Plumbing', `${b.fixtures.length} fixtures · water & drainage`, 2, disciplineChecks(r, 'plumbing')),
    b.fire?.enabled ? screened('fire', 'Fire protection', 'Occupancy, egress & provisions', 2, disciplineChecks(r, 'fire')) :
      {id: 'fire', title: 'Fire protection', detail: 'Confirm supported occupancy to begin', group: 2, state: 'idle', label: 'Not screened'},
    b.solar?.enabled ? screened('solar', 'Solar PV', 'Array, roof loading & connection', 2, disciplineChecks(r, 'solar')) :
      {id: 'solar', title: 'Solar PV', detail: 'Add an array when your project needs it', group: 2, state: 'optional', label: 'Optional'},
    {id: 'quantities', title: 'Quantities & cost', detail: `${r.quantities.items.length} quantity lines · demo rates`, group: 3,
      state: r.stale ? 'stale' : r.quantities.unpriced?.length ? 'missing' : r.quantities.items.length ? 'ready' : 'missing',
      label: r.stale ? 'Recompute' : r.quantities.unpriced?.length ? 'Unpriced items' : r.quantities.items.length ? 'Estimate calculated' : 'No quantities'},
  ];
  // A saved revision is not a professional approval. Handoff stays explicit about review.
  const pending = revision.status === 'candidate';
  const unresolved = stages.some(s => !['ready', 'optional'].includes(s.state));
  stages.push({id: 'handoff', title: 'Review & export', group: 3,
    state: r.stale ? 'stale' : pending || unresolved ? 'attention' : 'ready',
    label: r.stale ? 'Recompute' : pending ? 'Candidate to review' : unresolved ? 'Review open items' : 'Package available',
    detail: 'Compare changes · export for professional review'});
  return stages;
}
