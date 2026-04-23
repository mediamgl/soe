import React from 'react';
import { Outlet } from 'react-router-dom';
import ProgressStepper from './ProgressStepper';

export default function AssessmentLayout() {
  return (
    <div className="max-w-content mx-auto px-6 sm:px-8 pt-10 sm:pt-14 pb-8">
      <ProgressStepper />
      <div className="mt-12 sm:mt-16">
        <Outlet />
      </div>
    </div>
  );
}
