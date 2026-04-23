import React from 'react';
import StagePlaceholder from './StagePlaceholder';

export default function Processing() {
  return (
    <StagePlaceholder
      eyebrow="Analysis"
      title="Processing Your Assessment"
      description="Your responses are being synthesised across the six transformation-readiness dimensions. This typically takes a few moments."
      backTo="/assessment/scenario"
      nextTo="/assessment/results"
      nextLabel="View results"
    />
  );
}
