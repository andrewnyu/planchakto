import {useEffect, useRef, useState} from 'react';
import {ArrowRight, AtSign, Check, CheckCircle2, FileText, GitBranch, Loader2, Paperclip, Plus, Send, Sparkles, X} from 'lucide-react';
import {money} from './api';
import {composeDecisionReply, hasAllDecisions, recommendedDecisions, usesRecommendations, type DecisionQuestion, type DecisionSelection} from './agentDecisions';

export type Thread = {id: string; name: string; messages: {role: 'user' | 'assistant'; text: string; outcome?: string; candidate_revision_id?: string; questions?: DecisionQuestion[]}[]};
export type Sketch = {name: string; mime_type: string; data: string; url: string};
type Suggestion = {label: string; run: () => void; disabled?: boolean};

const providerName: Record<string, string> = {gemini: 'Gemini', vertex: 'Gemini · Vertex AI', openrouter: 'OpenRouter'};

/** Cursor-style agent docked beside the plan: one persistent conversation, the current selection as context, candidates to review. */
export function AgentPanel({provider, model, visionModel, contextName, revisionId, thread, pending, working, reply, message, sketch, suggestions,
  onMessage, onAsk, onAttach, onRemoveSketch, onNewThread, onReview, onClose}: {
  provider: string | null; model: string | null; visionModel: string | null; contextName: string; revisionId: string; thread: Thread | null;
  pending: string; working: string; reply: any; message: string; sketch: Sketch | null; suggestions: Suggestion[];
  onMessage: (text: string) => void; onAsk: (message?: string) => void; onAttach: (file?: File) => void; onRemoveSketch: () => void; onNewThread: () => void;
  onReview: (revisionId: string) => void; onClose: () => void;
}) {
  const scroll = useRef<HTMLDivElement>(null), input = useRef<HTMLTextAreaElement>(null);
  const [decisions, setDecisions] = useState<DecisionSelection>({});
  const messages = thread?.messages ?? [];
  const lastMessage = messages.at(-1), questions = lastMessage?.role === 'assistant' ? lastMessage.questions ?? [] : [];
  useEffect(() => {input.current?.focus();}, []);
  useEffect(() => {scroll.current?.scrollTo({top: scroll.current.scrollHeight, behavior: 'smooth'});}, [messages.length, pending, working]);
  useEffect(() => {setDecisions(recommendedDecisions(questions));}, [thread?.id, messages.length]);
  const canSend = !!provider && !working && (!!message.trim() || !!sketch);
  const evidence = reply?.evidence; const summary = evidence?.summary; const delta = evidence?.comparison?.cost_delta;
  return <aside className="agent-panel" aria-label="Design agent">
    <header className="agent-panel-head">
      <div><Sparkles size={15}/><strong>Agent</strong><span className={'agent-dot' + (provider ? ' live' : '')} title={provider ? 'Connected' : 'Not connected'}/></div>
      <div><button className="icon-button" aria-label="New conversation" title="New conversation" disabled={!!working} onClick={onNewThread}><Plus size={15}/></button>
        <button className="icon-button" aria-label="Close agent" title="Close (⌘L)" onClick={onClose}><X size={15}/></button></div>
    </header>
    <div ref={scroll} className="agent-panel-scroll" aria-live="polite">
      {messages.length === 0 && !pending && <div className="agent-empty">
        <p>{provider ? 'Ask for a change in plain language. Every edit becomes a candidate revision with its checks and cost, and nothing is applied until you accept it.' : 'Connect Gemini or OpenRouter on the server to use the agent. The manual tools below still work.'}</p>
        <div className="agent-suggestions">{suggestions.map(s => <button key={s.label} disabled={s.disabled || !!working} onClick={s.run}>{s.label}<ArrowRight size={12}/></button>)}</div>
      </div>}
      {messages.map((m, i) => <div key={i} className={'agent-msg ' + m.role}>
        {m.role === 'assistant' && <span className="agent-msg-icon">{m.outcome === 'built' ? <CheckCircle2 size={12}/> : <Sparkles size={12}/>}</span>}
        <div><p>{m.text}</p>{m.candidate_revision_id && <button className="agent-candidate" onClick={() => onReview(m.candidate_revision_id!)}><GitBranch size={12}/> Review candidate on the plan <ArrowRight size={12}/></button>}
          {i === messages.length - 1 && m.role === 'assistant' && questions.length > 0 && <div className="agent-decisions">
            <div className="agent-decisions-head"><strong>{questions.length === 1 ? 'One decision needed' : `${questions.length} decisions needed`}</strong><span>Recommended choices are preselected</span></div>
            {questions.map((question, questionIndex) => <fieldset key={question.id} className="agent-decision">
              <legend><span>{questionIndex + 1}</span>{question.question}</legend>
              <div role="radiogroup" aria-label={question.question}>{question.options.map((option, optionIndex) => {
                const recommended = option.recommended || (!question.options.some(choice => choice.recommended) && optionIndex === 0);
                const selected = decisions[question.id] === option.response;
                return <button type="button" role="radio" aria-checked={selected} disabled={!!working} key={option.response} className={'agent-choice' + (selected ? ' selected' : '')}
                  onClick={() => setDecisions(current => ({...current, [question.id]: option.response}))}>
                  <span className="agent-choice-mark">{selected && <Check size={12}/>}</span><span><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</span>{recommended && <em>Recommended</em>}
                </button>;
              })}</div>
            </fieldset>)}
            <button type="button" className="agent-decision-send" disabled={!!working || !hasAllDecisions(questions, decisions)} onClick={() => onAsk(composeDecisionReply(questions, decisions))}>
              {usesRecommendations(questions, decisions) ? 'Send recommended decisions' : 'Send decisions'}<ArrowRight size={13}/>
            </button>
          </div>}
        </div>
      </div>)}
      {pending && <div className="agent-msg user"><div><p>{pending}</p></div></div>}
      {working && <div className="agent-msg assistant working"><span className="agent-msg-icon"><Loader2 className="spin" size={12}/></span><div><p>{working}</p><small>Typed commands are validated and dry-run against the layout checks before you see them.</small></div></div>}
      {!working && reply && (summary || delta != null) && <div className="agent-evidence">
        {summary && <span><b>{summary.pass}</b> pass · <b className={summary.fail ? 'bad' : ''}>{summary.fail}</b> fail · {summary.missing_input} missing</span>}
        {delta != null && <span>Cost {delta >= 0 ? '+' : ''}{money(delta)}</span>}
        <details><summary>Evidence</summary><pre>{JSON.stringify(evidence, null, 2)}</pre></details>
      </div>}
    </div>
    <form className="agent-composer" onSubmit={e => {e.preventDefault(); if (canSend) onAsk();}}>
      <div className="agent-context"><span title="Selected element"><AtSign size={11}/>{contextName}</span><span className="mono" title="Revision">{revisionId.slice(-8)}</span>
        {sketch && <span className="agent-sketch">{sketch.mime_type.startsWith('image/') ? <img src={sketch.url} alt=""/> : <FileText size={11}/>}{sketch.name}<button type="button" aria-label="Remove attached drawing" onClick={onRemoveSketch}><X size={10}/></button></span>}</div>
      <textarea ref={input} rows={3} value={message} disabled={!provider} aria-label="Message the design agent" placeholder={provider ? (sketch ? 'Arrange the rooms like this drawing…' : 'Ask for a change, or ask why a check fails…') : 'Agent not connected'}
        onChange={e => onMessage(e.target.value)} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey) {e.preventDefault(); e.currentTarget.form?.requestSubmit();}}}/>
      <div className="agent-composer-foot">
        <label className="icon-button" title={`Attach a sketch, photo or plan (read by ${visionModel || model || 'Gemini'})`}><input type="file" hidden accept="image/png,image/jpeg,image/webp,application/pdf" disabled={!provider} onChange={e => {onAttach(e.target.files?.[0]); e.target.value = '';}}/><Paperclip size={14}/></label>
        <span className="agent-model">{provider ? `${providerName[provider] ?? provider} · ${model}` : 'offline'}</span>
        <button className="agent-send" aria-label="Send" disabled={!canSend}><Send size={13}/></button>
      </div>
    </form>
  </aside>;
}
