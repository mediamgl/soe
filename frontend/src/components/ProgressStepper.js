import React from 'react';
import { useLocation } from 'react-router-dom';
import { Check } from 'lucide-react';
import { ASSESSMENT_STAGES } from '../context/AssessmentContext';

const STAGES_WITH_SHORT = [
  { ...ASSESSMENT_STAGES[0], short: 'Psych.' },
  { ...ASSESSMENT_STAGES[1], short: 'AI' },
  { ...ASSESSMENT_STAGES[2], short: 'Scen.' },
  { ...ASSESSMENT_STAGES[3], short: 'Proc.' },
  { ...ASSESSMENT_STAGES[4], short: 'Results' },
];

function stepState(index, activeIndex) {
  if (index < activeIndex) return 'complete';
  if (index === activeIndex) return 'current';
  return 'upcoming';
}

export default function ProgressStepper() {
  const { pathname } = useLocation();
  const activeIndex = Math.max(
    0,
    ASSESSMENT_STAGES.findIndex((s) => s.path === pathname)
  );

  return (
    <nav aria-label="Assessment progress" className="w-full">
      <ol className="grid grid-cols-5 items-start gap-0">
        {STAGES_WITH_SHORT.map((stage, index) => {
          const state = stepState(index, activeIndex);
          const isFirst = index === 0;
          const isLast = index === STAGES_WITH_SHORT.length - 1;
          return (
            <li
              key={stage.id}
              className="flex flex-col items-center min-w-0"
              aria-current={state === 'current' ? 'step' : undefined}
            >
              {/* Circle row with connectors */}
              <div className="flex items-center w-full">
                {/* left connector */}
                <div className="flex-1 h-px">
                  {!isFirst && (
                    <div
                      className={
                        'h-px w-full ' +
                        (index <= activeIndex ? 'bg-gold' : 'bg-hairline')
                      }
                    />
                  )}
                </div>
                {/* circle */}
                <div className="flex items-center justify-center flex-none">
                  {state === 'complete' && (
                    <span
                      className="flex items-center justify-center w-8 h-8 rounded-full bg-gold text-white shadow-sm"
                      aria-label="Completed"
                    >
                      <Check className="w-4 h-4" strokeWidth={3} />
                    </span>
                  )}
                  {state === 'current' && (
                    <span className="flex items-center justify-center w-8 h-8 rounded-full bg-navy text-white text-sm font-medium shadow-sm">
                      {index + 1}
                    </span>
                  )}
                  {state === 'upcoming' && (
                    <span className="flex items-center justify-center w-8 h-8 rounded-full border border-hairline text-muted text-sm font-medium bg-white">
                      {index + 1}
                    </span>
                  )}
                </div>
                {/* right connector */}
                <div className="flex-1 h-px">
                  {!isLast && (
                    <div
                      className={
                        'h-px w-full ' +
                        (index < activeIndex ? 'bg-gold' : 'bg-hairline')
                      }
                    />
                  )}
                </div>
              </div>
              {/* Label — short on mobile, full on sm+ */}
              <span
                className={
                  'mt-3 text-[10px] sm:text-xs tracking-wider2 uppercase text-center leading-tight px-1 ' +
                  (state === 'current'
                    ? 'text-navy font-semibold'
                    : state === 'complete'
                    ? 'text-gold-dark font-medium'
                    : 'text-muted')
                }
              >
                <span className="sm:hidden">{stage.short}</span>
                <span className="hidden sm:inline">{stage.label}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
