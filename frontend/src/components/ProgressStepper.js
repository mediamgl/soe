import React from 'react';
import { useLocation } from 'react-router-dom';
import { Check } from 'lucide-react';

const STAGES = [
  { id: 'psychometric', label: 'Psychometric', short: 'Psych.', path: '/assessment/psychometric' },
  { id: 'ai-discussion', label: 'AI Discussion', short: 'AI', path: '/assessment/ai-discussion' },
  { id: 'scenario', label: 'Scenario', short: 'Scen.', path: '/assessment/scenario' },
  { id: 'processing', label: 'Processing', short: 'Proc.', path: '/assessment/processing' },
  { id: 'results', label: 'Results', short: 'Results', path: '/assessment/results' },
];

function stepState(index, activeIndex) {
  if (index < activeIndex) return 'complete';
  if (index === activeIndex) return 'current';
  return 'upcoming';
}

export default function ProgressStepper() {
  const { pathname } = useLocation();
  const activeIndex = Math.max(0, STAGES.findIndex((s) => s.path === pathname));

  return (
    <nav aria-label="Assessment progress" className="w-full">
      <ol className="grid grid-cols-5 items-start gap-0">
        {STAGES.map((stage, index) => {
          const state = stepState(index, activeIndex);
          const isFirst = index === 0;
          const isLast = index === STAGES.length - 1;
          return (
            <li
              key={stage.id}
              className="flex flex-col items-center min-w-0"
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <div className="flex items-center w-full">
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
