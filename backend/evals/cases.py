"""Representative conversations for the new-project design assistant (scripts/eval_assistant.py runs them live).

Each case is a list of user turns on a template, plus expectations about where the conversation should end. Every case
is also held to the invariants in runner.py: valid output on every turn, a buildable project at the end, no project
change on clarification or unsupported turns, and no budget or site value the user did not give.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Callable
from ..compose import ProjectSpec


@dataclass
class State:
    initial: ProjectSpec
    spec: ProjectSpec
    turns: list[dict]

    @property
    def last(self): return self.turns[-1]


@dataclass
class Case:
    id: str
    template: str
    category: str  # basic | correction | ambiguous | unsupported | conflict | question | grounding
    turns: list[str]
    expect: list[tuple[str, Callable[[State], bool]]]
    decides: tuple[str, ...] = ()  # protected fields the user supplies in these turns
    notes: str = ''


def rooms(s: ProjectSpec, *words) -> list:
    return [r for r in s.rooms if any(w in r.name.lower() for w in words)]
def count(s: ProjectSpec, *words) -> int: return sum(r.count for r in rooms(s, *words))
def kind(s: ProjectSpec, k: str) -> int: return sum(r.count for r in s.rooms if r.kind == k)
def area(s: ProjectSpec, *words) -> float | None:
    found = rooms(s, *words); return found[0].area if found else None
def unchanged(st: State) -> bool: return st.spec == st.initial
def outcome(*names): return lambda st: st.last['outcome'] in names
def says(pattern): return lambda st: re.search(pattern, st.last['reply'], re.I) is not None


CASES: list[Case] = [
    # House
    Case('house-basic', 'house', 'basic', ['A 3-bedroom family house in Tagaytay.'],
         [('3 bedrooms', lambda st: kind(st.spec, 'bedroom') == 3), ('location Tagaytay', lambda st: 'tagaytay' in (st.spec.location or '').lower())]),
    Case('house-home-office', 'house', 'basic', ['Add a home office of about 10 m².'],
         [('an office room', lambda st: kind(st.spec, 'office') >= 1), ('about 10 m²', lambda st: 8 <= (area(st.spec, 'office') or 0) <= 12)]),
    Case('house-bigger-kitchen', 'house', 'basic', ['Make the kitchen bigger, around 15 square metres.'],
         [('kitchen ~15 m²', lambda st: 13 <= (area(st.spec, 'kitchen') or 0) <= 17)]),
    Case('house-correction-bedrooms', 'house', 'correction', ['Add two more bedrooms.', 'Actually, only one extra bedroom, not two.'],
         [('3 bedrooms in total', lambda st: kind(st.spec, 'bedroom') == 3)]),
    Case('house-correction-name', 'house', 'correction', ['Call it Casa Reyes.', 'Sorry, I meant Casa Reyes-Santos.'],
         [('renamed', lambda st: (st.spec.name or '') == 'Casa Reyes-Santos')]),
    Case('house-drop-bedroom', 'house', 'basic', ["We don't need the second bedroom."],
         [('one bedroom left', lambda st: kind(st.spec, 'bedroom') == 1)]),
    Case('house-ambiguous-bigger', 'house', 'ambiguous', ['Make it bigger.'],
         [('asks instead of guessing', outcome('clarification')), ('project unchanged', unchanged)]),
    Case('house-two-storey', 'house', 'unsupported', ['Make it a two-storey house with the bedrooms upstairs.'],
         [('declined as unsupported', outcome('unsupported')), ('project unchanged', unchanged), ('explains the limit', says(r'single|one[ -]stor|storey'))]),
    Case('house-negated-storey', 'house', 'basic', ['Keep it single storey, not two-storey, and add a 6 m² laundry room.'],
         [('edits applied', outcome('updated')), ('laundry added', lambda st: count(st.spec, 'laundry') == 1)]),
    Case('house-budget', 'house', 'grounding', ['Our budget is 2 million pesos.'],
         [('budget set', lambda st: st.spec.budget == 2e6), ('quotes the estimate', says(r'₱|php|peso|million|estimate'))], decides=('budget',)),
    Case('house-explain-soil', 'house', 'question', ['What does soil profile SD mean?'],
         [('answers without editing', outcome('answer')), ('project unchanged', unchanged), ('mentions soil', says(r'soil'))]),
    Case('house-oversize', 'house', 'conflict', ['Add 12 bedrooms of 50 m² each and a 300 m² living room.'],
         [('does not pretend it fits', lambda st: st.last['outcome'] in ('unsupported', 'clarification') or st.last['plan_ok'])]),
    # Commercial
    Case('clinic-brief', 'commercial', 'basic', ['A dental clinic in Cebu City called Ngiti Dental, with 3 treatment rooms, a waiting area for 12, '
                                               'a sterilisation room, an office, two toilets and a pantry.'],
         [('3 treatment rooms', lambda st: count(st.spec, 'treatment') == 3), ('named', lambda st: 'ngiti' in (st.spec.name or '').lower()),
          ('in Cebu', lambda st: 'cebu' in (st.spec.location or '').lower()), ('two toilets', lambda st: kind(st.spec, 'bathroom') == 2)]),
    Case('office-rooms', 'commercial', 'basic', ['Three private offices of 12 m² each and a meeting room for 10 people.'],
         [('3+ offices', lambda st: kind(st.spec, 'office') >= 3), ('meeting room', lambda st: count(st.spec, 'meeting') >= 1)]),
    Case('call-centre', 'commercial', 'basic', ["It's a call centre."],
         [('concentrated occupancy or asks', lambda st: st.spec.fire_occupancy == 'business_concentrated' or 'fire_occupancy' in st.last['questions'])]),
    Case('server-room-correction', 'commercial', 'correction', ['Add a 20 m² server room.', 'Make the server room 15 m² instead.'],
         [('server room 15 m²', lambda st: area(st.spec, 'server') == 15), ('only one server room', lambda st: count(st.spec, 'server') == 1)]),
    Case('stockroom-restore', 'commercial', 'correction', ['Remove the stockroom.', 'Bring the stockroom back at 25 m².'],
         [('stockroom back at 25 m²', lambda st: area(st.spec, 'stock') == 25)]),
    Case('ambiguous-that-room', 'commercial', 'ambiguous', ['Double the size of that room.'],
         [('asks which room', outcome('clarification')), ('project unchanged', unchanged)]),
    Case('basement', 'commercial', 'unsupported', ['Add a basement parking level.'],
         [('declined', outcome('unsupported')), ('project unchanged', unchanged)]),
    Case('l-shape', 'commercial', 'unsupported', ['Make the building L-shaped around a courtyard.'],
         [('declined', outcome('unsupported')), ('project unchanged', unchanged)]),
    Case('pharmacy-no-guessing', 'commercial', 'basic', ['A small pharmacy in Davao.'],
         [('location Davao', lambda st: 'davao' in (st.spec.location or '').lower()),
          ('site values left open', lambda st: all(getattr(st.spec, f) is None for f in ('budget', 'fault_distance', 'soil_profile', 'friction')))]),
    Case('budget-conflict', 'commercial', 'grounding', ['Our budget is 3 million pesos.', 'Add a 100 m² showroom extension, so the showroom is 160 m².'],
         [('budget kept', lambda st: st.spec.budget == 3e6), ('showroom 160 m²', lambda st: area(st.spec, 'showroom') == 160),
          ('talks about the budget', says(r'budget|over|under|within'))], decides=('budget',)),
    Case('why-rear-exit', 'commercial', 'question', ['Why would I want a rear exit?'],
         [('answers', outcome('answer')), ('project unchanged', unchanged)]),
    Case('solar', 'commercial', 'basic', ['Add 10 kWp of rooftop solar.'], [('solar 10', lambda st: st.spec.solar == '10')]),
    Case('eave-height', 'commercial', 'basic', ['Raise the eave height to 4 m.'], [('height 4 m', lambda st: st.spec.height == 4)]),
    Case('rename-then-question', 'commercial', 'correction', ['Call it Sari Hub.', 'What is the footprint now?'],
         [('name kept', lambda st: (st.spec.name or '') == 'Sari Hub'), ('answers with a size', says(r'\d+(\.\d+)?\s*(m|×|x)'))]),
    # Warehouse
    Case('warehouse-brief', 'warehouse', 'basic', ['A dry-goods warehouse in Valenzuela with a 400 m² storage hall, two loading bays and a dispatch office.'],
         [('hall ~400 m²', lambda st: 380 <= (area(st.spec, 'storage hall', 'hall') or 0) <= 420), ('two loading bays', lambda st: count(st.spec, 'loading') == 2),
          ('in Valenzuela', lambda st: 'valenzuela' in (st.spec.location or '').lower())]),
    Case('mezzanine', 'warehouse', 'unsupported', ['Add a mezzanine office floor above the loading bay.'],
         [('declined', outcome('unsupported')), ('project unchanged', unchanged)]),
    Case('hall-correction', 'warehouse', 'correction', ['Make the storage hall 350 m².', 'No wait, 250 m².'],
         [('hall 250 m²', lambda st: area(st.spec, 'storage hall', 'hall') == 250)]),
    Case('hall-oversize', 'warehouse', 'conflict', ['Make the storage hall 1,200 m².'],
         [('does not pretend it fits', lambda st: st.last['outcome'] in ('unsupported', 'clarification') or st.last['plan_ok'])]),
    Case('some-toilets', 'warehouse', 'ambiguous', ['Add some more toilets.'],
         [('asks how many or adds a sensible number', lambda st: st.last['outcome'] == 'clarification' or 2 <= kind(st.spec, 'bathroom') <= 4)]),
    Case('multi-edit', 'warehouse', 'basic', ['Rename it Valenzuela Hub, add a 12 m² guard house, and fill the roof with solar.'],
         [('renamed', lambda st: (st.spec.name or '') == 'Valenzuela Hub'), ('guard house', lambda st: area(st.spec, 'guard') == 12),
          ('solar fill', lambda st: st.spec.solar == 'fill')]),
]
