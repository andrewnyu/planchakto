import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {composeDecisionReply, hasAllDecisions, recommendedDecisions, usesRecommendations, type DecisionQuestion} from '../src/agentDecisions.ts';

const questions: DecisionQuestion[] = [
  {id: 'distance', question: 'How far should the corridor move?', options: [
    {label: 'Move 1.5 m', response: 'Move the corridor down by 1.5 m.', recommended: true},
    {label: 'Move 1.0 m', response: 'Move the corridor down by 1.0 m.'},
  ]},
  {id: 'rooms', question: 'How should adjacent rooms respond?', options: [
    {label: 'Resize together', response: 'Resize the adjacent rooms together.', recommended: true},
    {label: 'Keep bedrooms', response: 'Keep both bedrooms unchanged.'},
  ]},
];

test('recommended decisions are immediately ready to send', () => {
  const selections = recommendedDecisions(questions);
  assert.equal(hasAllDecisions(questions, selections), true);
  assert.equal(usesRecommendations(questions, selections), true);
  assert.match(composeDecisionReply(questions, selections), /1\. How far.*\nMove the corridor down by 1\.5 m\./s);
});

test('changing one answer preserves a complete conversational reply', () => {
  const selections = {...recommendedDecisions(questions), rooms: 'Keep both bedrooms unchanged.'};
  assert.equal(usesRecommendations(questions, selections), false);
  assert.match(composeDecisionReply(questions, selections), /2\. How should adjacent rooms respond\?\nKeep both bedrooms unchanged\./);
});
