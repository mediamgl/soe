import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, KeyRound } from 'lucide-react';
import ResumeModal from '../components/ResumeModal';

export default function Landing() {
  const [resumeOpen, setResumeOpen] = useState(false);

  return (
    <section className="max-w-content mx-auto px-6 sm:px-8 pt-20 sm:pt-32 pb-24">
      <div className="max-w-3xl mx-auto text-center">
        <span className="eyebrow">Executive Assessment</span>
        <h1 className="mt-6 text-4xl sm:text-5xl md:text-6xl font-serif text-navy leading-tight tracking-tight">
          Transformation Readiness Assessment
        </h1>
        <div className="mt-8 mx-auto gold-rule" aria-hidden="true" />
        <p className="mt-8 text-lg sm:text-xl text-ink/80 font-sans leading-relaxed">
          Experience the AI-powered methodology for assessing leadership transformation readiness
        </p>
        <p className="mt-6 text-base text-muted max-w-2xl mx-auto leading-relaxed">
          This 35–45 minute assessment evaluates six critical dimensions of transformation capability using
          psychometric measures, AI-facilitated discussion, and strategic scenario analysis.
        </p>
        <div className="mt-12 flex flex-col sm:flex-row items-center justify-center gap-6">
          <Link to="/start" className="btn-primary">
            Begin Assessment
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </Link>
          <button
            type="button"
            onClick={() => setResumeOpen(true)}
            className="inline-flex items-center gap-2 text-sm uppercase tracking-wider2 text-navy font-medium border-b border-transparent hover:border-gold hover:text-navy-dark transition-colors"
          >
            <KeyRound className="w-4 h-4" strokeWidth={2} /> Resume a session
          </button>
        </div>
      </div>

      <ResumeModal open={resumeOpen} onClose={() => setResumeOpen(false)} />
    </section>
  );
}
