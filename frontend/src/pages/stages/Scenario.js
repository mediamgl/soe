import React from 'react';
import StagePlaceholder from './StagePlaceholder';

export default function Scenario() {
  return (
    <StagePlaceholder
      eyebrow="Stage 3 of 3"
      title="Strategic Scenario"
      description="Analyse a complex situation and respond to new information as it emerges. This stage evaluates how you reason under ambiguity and update your thinking."
      backTo="/assessment/ai-discussion"
      nextTo="/assessment/processing"
      nextLabel="Submit for analysis"
    />
  );
}
