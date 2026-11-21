import {useId} from 'react';
import {ArrowUpRight, ChevronDown} from 'lucide-react';
import './planningAgents.css';

export type PlanningAgent = {
  role: string;
  label: string;
  status: string;
  summary?: string;
  no_ai_review?: boolean;
};

export type PlanningAgentsProps = {
  roster: PlanningAgent[];
  reviews: Record<string, any>;
  busy: boolean;
  aiAvailable: boolean;
  /** True only when deterministic analysis matches the accepted design and inputs. */
  current: boolean;
  onReview: (role: string) => void;
  onLocate: (id: string) => void;
};

const roles = [
  {role: 'architecture', label: 'Architecture agent', scope: 'Spaces, programme and circulation'},
  {role: 'structure', label: 'Structural agent', scope: 'Supported structural screens and their limits'},
  {role: 'fire_accessibility', label: 'Fire & accessibility agent', scope: 'Egress, access and outstanding provisions'},
  {role: 'electrical', label: 'Electrical agent', scope: 'Confirmed loads and electrical screen findings'},
  {role: 'plumbing', label: 'Plumbing agent', scope: 'Water, drainage and missing service inputs'},
  {role: 'site_traffic', label: 'Site & traffic agent', scope: 'Site access, parking and delivery circulation'},
  {role: 'quantities', label: 'Quantities agent', scope: 'Modelled quantities, rates and exclusions'},
];

const statusLabels: Record<string, string> = {
  ready: 'Ready for review',
  available: 'Ready for review',
  advisory_ready: 'Ready for review',
  current: 'Current screens available',
  reviewed: 'Review available',
  complete: 'Review available',
  live: 'Review available',
  attention: 'Findings to review',
  fail: 'Findings to review',
  warning: 'Warnings to review',
  missing: 'Missing inputs',
  missing_input: 'Missing inputs',
  needs_inputs: 'Missing inputs',
  blocked: 'Review blocked',
  unsupported: 'Unsupported',
  not_checked: 'Not checked',
  stale: 'Earlier design or inputs',
  unavailable: 'AI unavailable',
  idle: 'No AI review yet',
  not_run: 'No AI review yet',
  not_reviewed: 'No AI review yet',
  no_ai_review: 'No AI review yet',
  pass: 'Supported screens calculated',
};

const text = (value: unknown): string => typeof value === 'string' ? value : '';
const strings = (value: unknown): string[] => Array.isArray(value)
  ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : [];

function ReviewEvidence({findingIds, inputPaths, context, stale, onLocate}: {
  findingIds: string[];
  inputPaths: string[];
  context: string;
  stale: boolean;
  onLocate: (id: string) => void;
}) {
  return <div className="planning-agent-evidence">
    <strong>Evidence</strong>
    {findingIds.length > 0 && <ul className="planning-agent-finding-links">{findingIds.map(finding => <li key={finding}>
      <button type="button" disabled={stale} onClick={() => onLocate(finding)} aria-label={`View finding ${finding} for ${context}`}>
        View finding {finding}<ArrowUpRight size={13} aria-hidden="true"/>
      </button>
    </li>)}</ul>}
    {inputPaths.length > 0 && <p className="planning-agent-input-evidence">Input fields: {inputPaths.map((path, i) => <span key={path}>{i > 0 && '; '}<code>{path}</code></span>)}</p>}
    {findingIds.length === 0 && inputPaths.length === 0 && <p>No finding or input reference supplied. Verify this advice before using it.</p>}
  </div>;
}

function reviewQuestions(value: unknown): Array<{question: string; finding_ids: string[]; input_paths: string[]}> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item: unknown) => {
    if (typeof item === 'string' && item.length > 0) return [{question: item, finding_ids: [], input_paths: []}];
    if (!item || typeof item !== 'object') return [];
    const question = item as Record<string, unknown>;
    return text(question.question) ? [{question: text(question.question), finding_ids: strings(question.finding_ids), input_paths: strings(question.input_paths)}] : [];
  });
}

export function PlanningAgents({roster, reviews, busy, aiAvailable, current, onReview, onLocate}: PlanningAgentsProps) {
  const id = useId();
  const supplied = new Map(roster.map(agent => [agent.role, agent]));
  const agents = [
    ...roles.map(role => ({...role, status: 'not_reviewed', ...supplied.get(role.role)})),
    ...roster.filter(agent => !roles.some(role => role.role === agent.role)).map(agent => ({...agent, scope: ''})),
  ];
  const disabledReason = !current
    ? 'Run screens for the accepted design and confirmed inputs before requesting a specialist review.'
    : !aiAvailable
      ? 'AI is unavailable. Connect a provider to request a specialist review.'
      : busy ? 'A workspace action is running. Request a review when it finishes.' : '';

  return <section className="planning-agents" aria-labelledby={`${id}-heading`}>
    <header>
      <h3 id={`${id}-heading`}>Specialist agents</h3>
      <p>Each agent reviews the same accepted design and its screen evidence. Advice is for your review; agents make no autonomous edits.</p>
    </header>
    <p className={`planning-agents-context${!current ? ' is-stale' : ''}`} id={`${id}-availability`}>
      {disabledReason || 'Current screens available. Choose a specialist to review the findings with AI.'}
    </p>
    <ul className="planning-agent-roster" aria-label="Specialist review status">
      {agents.map(agent => {
        const review = reviews[agent.role];
        const hasReview = review?.mode === 'live' && !review.no_ai_review && agent.no_ai_review !== true;
        const bound = !!text(review?.design_hash) && !!text(review?.inputs_hash);
        const stale = !current || !bound || agent.status === 'stale' || review?.stale === true;
        const recommendations = hasReview && Array.isArray(review.recommendations)
          ? review.recommendations.filter((item: unknown) => item && typeof item === 'object') : [];
        const questions = hasReview ? reviewQuestions(review.questions) : [];
        const label = agent.label || agent.role.replaceAll('_', ' ');
        const status = statusLabels[agent.status] || agent.status.replaceAll('_', ' ') || 'Status unavailable';
        const reviewStatus = hasReview
          ? stale ? 'AI review from earlier screens' : 'AI review available'
          : 'No AI review yet';
        const reviewId = `${id}-${agent.role}-review-status`;

        return <li key={agent.role} className="planning-agent-entry">
          <div className="planning-agent-row">
            <div className="planning-agent-identity">
              <h4>{label}</h4>
              <p>{agent.scope}</p>
            </div>
            <div className="planning-agent-state" id={reviewId}>
              <span className={`planning-agent-status status-${agent.status}`}>{status}</span>
              <span>{reviewStatus}</span>
            </div>
            <button type="button" className="planning-agent-request" disabled={busy || !aiAvailable || !current}
              aria-describedby={`${id}-availability ${reviewId}`} onClick={() => onReview(agent.role)}>
              {hasReview ? 'Review again with ' : 'Review with '}{label}
            </button>
          </div>
          {agent.summary && <p className="planning-agent-screen-summary">{agent.summary}</p>}
          {hasReview && <details className="planning-agent-review">
            <summary><ChevronDown size={14} aria-hidden="true"/><span>Read {label.toLowerCase()} review</span><span className="planning-agent-count">{recommendations.length} recommendation{recommendations.length === 1 ? '' : 's'}</span></summary>
            <div className="planning-agent-review-content">
              <p className="planning-agent-review-source">AI advisory review{stale ? ' · Earlier screens; run current screens and request a new review before using this advice.' : ' · Based on the accepted design and confirmed inputs.'}</p>
              {text(review.summary) && <p>{text(review.summary)}</p>}
              <ReviewEvidence findingIds={strings(review.finding_ids)} inputPaths={strings(review.input_paths)} context={`${label} summary`} stale={stale} onLocate={onLocate}/>
              {recommendations.length > 0 ? <ol className="planning-agent-recommendations">
                {recommendations.map((recommendation: Record<string, unknown>, index: number) => {
                  const findingIds = strings(recommendation.finding_ids);
                  const inputPaths = strings(recommendation.input_paths);
                  return <li key={`${text(recommendation.title)}-${index}`}>
                    <h5>{text(recommendation.title) || 'Recommendation'}</h5>
                    {text(recommendation.rationale) && <p>{text(recommendation.rationale)}</p>}
                    {text(recommendation.suggested_next_action) && <p><strong>Next step:</strong> {text(recommendation.suggested_next_action)}</p>}
                    <ReviewEvidence findingIds={findingIds} inputPaths={inputPaths} context={text(recommendation.title) || label} stale={stale} onLocate={onLocate}/>
                  </li>;
                })}
              </ol> : <p>No recommendations were returned. This does not establish that the design passes any screen.</p>}
              {questions.length > 0 && <div className="planning-agent-questions"><h5>Questions to resolve</h5><ul>{questions.map((question, index) => <li key={index}>
                <p>{question.question}</p>
                <ReviewEvidence findingIds={question.finding_ids} inputPaths={question.input_paths} context={question.question} stale={stale} onLocate={onLocate}/>
              </li>)}</ul></div>}
            </div>
          </details>}
        </li>;
      })}
    </ul>
    <p className="planning-agents-limit">Preliminary planning advice. Missing inputs and unsupported checks remain open. Licensed professional review is required.</p>
  </section>;
}
