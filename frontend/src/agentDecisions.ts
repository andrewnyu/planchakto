export type DecisionOption = {label: string; description?: string; response: string; recommended?: boolean};
export type DecisionQuestion = {id: string; question: string; options: DecisionOption[]};
export type DecisionSelection = Record<string, string>;

export function recommendedDecisions(questions: DecisionQuestion[]): DecisionSelection {
  return Object.fromEntries(questions.map(question => {
    const option = question.options.find(choice => choice.recommended) ?? question.options[0];
    return [question.id, option?.response ?? ''];
  }));
}

export function composeDecisionReply(questions: DecisionQuestion[], selections: DecisionSelection): string {
  return questions.map((question, index) => `${index + 1}. ${question.question}\n${selections[question.id]}`).join('\n\n');
}

export function hasAllDecisions(questions: DecisionQuestion[], selections: DecisionSelection): boolean {
  return questions.every(question => Boolean(selections[question.id]?.trim()));
}

export function usesRecommendations(questions: DecisionQuestion[], selections: DecisionSelection): boolean {
  const recommended = recommendedDecisions(questions);
  return questions.every(question => selections[question.id] === recommended[question.id]);
}
