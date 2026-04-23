import React from 'react';
import StagePlaceholder from './StagePlaceholder';

export default function Psychometric() {
  return (
    <StagePlaceholder
      eyebrow="Stage 1 of 3"
      title="Psychometric Assessment"
      description="Twenty questions measuring learning agility and tolerance for ambiguity. Answer as candidly as you can — there are no right or wrong answers."
      backTo="/context"
      backLabel="Back to overview"
      nextTo="/assessment/ai-discussion"
    />
  );
}
