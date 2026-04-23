import React from 'react';
import StagePlaceholder from './StagePlaceholder';

export default function AIDiscussion() {
  return (
    <StagePlaceholder
      eyebrow="Stage 2 of 3"
      title="AI Fluency Discussion"
      description="A conversation about your understanding and use of AI. The AI facilitator will adapt its questions to your responses."
      backTo="/assessment/psychometric"
      nextTo="/assessment/scenario"
    />
  );
}
