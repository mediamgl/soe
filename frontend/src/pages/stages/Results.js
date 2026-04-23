import React from 'react';
import StagePlaceholder from './StagePlaceholder';

export default function Results() {
  return (
    <StagePlaceholder
      eyebrow="Results"
      title="Your Readiness Profile"
      description="A summary of your transformation-readiness profile across the assessed dimensions, with narrative interpretation and development reflections."
      backTo="/assessment/processing"
      nextTo={null}
    />
  );
}
