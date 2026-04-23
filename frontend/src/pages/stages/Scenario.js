import React from 'react';
import StagePlaceholder from './StagePlaceholder';

export default function Scenario() {
  return (
    <StagePlaceholder
      stageKey="scenario"
      eyebrow="Stage 3 of 3"
      title="Strategic Scenario"
      description="Analyse a complex situation and respond to new information as it emerges. This stage evaluates how you reason under ambiguity and update your thinking."
      prevStage="ai-discussion"
      prevPath="/assessment/ai-discussion"
      nextStage="processing"
      nextPath="/assessment/processing"
      nextLabel="Submit for analysis"
    />
  );
}
