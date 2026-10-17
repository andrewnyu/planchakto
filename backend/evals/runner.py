"""Runs evaluation cases through the real design agent and checks the release invariants."""
from __future__ import annotations
import time, traceback
from ..agent import PROTECTED
from ..ai import compose_turn
from ..compose import ProjectSpec, compose, template_spec
from ..engine import compute
from .cases import Case, State


def run_case(case: Case, llm=None) -> dict:
    spec = template_spec(case.template); initial = spec; history: list[dict] = []; turns: list[dict] = []; problems: list[str] = []
    t = time.monotonic()
    for i, message in enumerate(case.turns):
        before = spec
        try: out = compose_turn(case.template, spec, history, message, llm=llm)
        except Exception as e:
            problems.append(f'turn {i + 1} failed: {type(e).__name__}: {str(e)[:200]}'); break
        if out['outcome'] in ('clarification', 'unsupported') and out['spec'] != before: problems.append(f'turn {i + 1} changed the project on {out["outcome"]}')
        if not out['reply'].strip(): problems.append(f'turn {i + 1} gave an empty reply')
        spec = out['spec']; history += [{'role': 'user', 'text': message}, {'role': 'assistant', 'text': out['reply']}]
        turns.append({'message': message, 'outcome': out['outcome'], 'reply': out['reply'], 'questions': [q['field'] for q in out['questions']],
                      'tools': out['tools'], 'plan_ok': out['plan'].get('plan_ok')})
    problems += invariant_problems(case, spec)
    expect = []
    if len(turns) == len(case.turns):
        st = State(initial, spec, turns)
        for label, check in case.expect:
            try: ok = bool(check(st))
            except Exception: ok = False
            expect.append({'label': label, 'ok': ok})
    return {'id': case.id, 'template': case.template, 'category': case.category, 'turns': turns, 'problems': problems, 'expect': expect,
            'passed': not problems and bool(expect) and all(e['ok'] for e in expect), 'seconds': round(time.monotonic() - t, 1),
            'spec': spec.model_dump(mode='json')}


def invariant_problems(case: Case, spec: ProjectSpec) -> list[str]:
    """Release gate: a valid, buildable project on the same template, with no budget or site value the user did not give."""
    out = []
    try: spec = ProjectSpec.model_validate(spec.model_dump())
    except Exception as e: return [f'invalid spec: {e}']
    if spec.template != case.template: out.append(f'template changed to {spec.template}')
    for f in PROTECTED:
        if getattr(spec, f) not in (None, 'unknown') and f not in case.decides: out.append(f'invented {f} = {getattr(spec, f)!r}')
    try: b, _ = compose(spec)
    except ValueError as e: out.append(f'ends unbuildable: {str(e)[:160]}'); return out
    except Exception: return out + ['corrupted project: ' + traceback.format_exc(limit=1).strip().splitlines()[-1]]
    try: compute(b, 'eval')
    except Exception as e: out.append(f'corrupted project: checks crashed ({type(e).__name__})')
    return out
