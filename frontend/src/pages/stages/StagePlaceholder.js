import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from 'lucide-react';

export default function StagePlaceholder({
  eyebrow,
  title,
  description,
  backTo,
  backLabel = 'Back',
  nextTo,
  nextLabel = 'Continue',
}) {
  return (
    <section className="max-w-3xl">
      <span className="eyebrow">{eyebrow}</span>
      <h1 className="mt-4 text-3xl sm:text-4xl md:text-5xl font-serif text-navy tracking-tight leading-tight">
        {title}
      </h1>
      <span className="mt-6 gold-rule block" aria-hidden="true" />
      <p className="mt-8 text-base sm:text-lg text-ink/75 leading-relaxed">{description}</p>

      <div className="mt-10 card border-dashed text-muted">
        <p className="text-sm tracking-wider2 uppercase text-gold font-medium">Coming in next phase</p>
        <p className="mt-3 text-sm text-ink/70 leading-relaxed">
          This stage is intentionally a placeholder in the current build. The full interaction
          (questions, conversation, or scenario) will be implemented in a subsequent phase.
        </p>
      </div>

      <div className="mt-12 flex items-center justify-between gap-4 flex-wrap">
        {backTo ? (
          <Link to={backTo} className="btn-ghost" aria-label={backLabel}>
            <ArrowLeft className="w-4 h-4" strokeWidth={2} />
            {backLabel}
          </Link>
        ) : (
          <span />
        )}
        {nextTo && (
          <Link to={nextTo} className="btn-primary">
            {nextLabel}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </Link>
        )}
      </div>
    </section>
  );
}
