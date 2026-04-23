import React, { createContext, useContext, useMemo, useState } from 'react';

export const ASSESSMENT_STAGES = [
  { id: 'psychometric', label: 'Psychometric', path: '/assessment/psychometric' },
  { id: 'ai-discussion', label: 'AI Discussion', path: '/assessment/ai-discussion' },
  { id: 'scenario', label: 'Scenario', path: '/assessment/scenario' },
  { id: 'processing', label: 'Processing', path: '/assessment/processing' },
  { id: 'results', label: 'Results', path: '/assessment/results' },
];

const AssessmentContext = createContext(null);

export function AssessmentProvider({ children }) {
  // Reserved for Phase 2+ (answers, session id, etc.). Kept minimal for Phase 1.
  const [sessionId] = useState(null);

  const value = useMemo(
    () => ({
      stages: ASSESSMENT_STAGES,
      sessionId,
    }),
    [sessionId]
  );

  return <AssessmentContext.Provider value={value}>{children}</AssessmentContext.Provider>;
}

export function useAssessment() {
  const ctx = useContext(AssessmentContext);
  if (!ctx) {
    throw new Error('useAssessment must be used inside AssessmentProvider');
  }
  return ctx;
}
