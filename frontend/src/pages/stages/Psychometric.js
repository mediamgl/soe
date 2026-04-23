import React from 'react';
import StagePlaceholder from './StagePlaceholder';

export default function Psychometric() {
  return (
    <StagePlaceholder
      stageKey="psychometric"
      eyebrow="Stage 1 of 3"
      title="Psychometric Assessment"
      description="Twenty questions measuring learning agility and tolerance for ambiguity. Answer as candidly as you can — there are no right or wrong answers."
      prevStage="context"
      prevPath="/context"
      nextStage="ai-discussion"
      nextPath="/assessment/ai-discussion"
      backLabel="Back to overview"
    />
  );
}
