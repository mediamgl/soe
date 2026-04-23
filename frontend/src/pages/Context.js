import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { useSession } from '../store/sessionStore';

const items = [
  {
    title: 'Psychometric Assessment',
    duration: '8–10 minutes',
    body: '20 questions measuring learning agility and tolerance for ambiguity.',
  },
  {
    title: 'AI Fluency Discussion',
    duration: '12–15 minutes',
    body: 'A conversation about your understanding and use of AI.',
  },
  {
    title: 'Strategic Scenario',
    duration: '10–12 minutes',
    body: 'Analyse a complex situation and respond to new information.',
  },
];

export default function Context() {
  const advanceStage = useSession((s) => s.advanceStage);
  const sessionId = useSession((s) => s.sessionId);
  const storeError = useSession((s) => s.error);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const navigate = useNavigate();

  async function onContinue() {
    setBusy(true);
    setErr(null);
    try {
      if (sessionId) {
        await advanceStage('psychometric');
      }
      navigate('/assessment/psychometric');
    } catch (e) {
      setErr(e.message || 'Could not continue.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="max-w-content mx-auto px-6 sm:px-8 pt-16 sm:pt-24 pb-20">
      <div className="max-w-3xl">
        <span className="eyebrow">Before You Begin</span>
        <h1 className="mt-4 text-3xl sm:text-4xl md:text-5xl font-serif text-navy tracking-tight leading-tight">
          What You’ll Experience
        </h1>
        <span className="mt-6 gold-rule block" aria-hidden="true" />
        <p className="mt-6 text-base sm:text-lg text-ink/75 leading-relaxed">
          The assessment is composed of three structured stages. Each stage focuses on a different
          facet of transformation capability.
        </p>
      </div>

      <div className="mt-14 grid gap-6 md:gap-8 md:grid-cols-3">
        {items.map((item, i) => (
          <article key={item.title} className="card card-gold-top">
            <span className="eyebrow">Stage {i + 1}</span>
            <h2 className="mt-3 text-xl sm:text-2xl font-serif text-navy leading-snug">
              {item.title}
            </h2>
            <div className="mt-4 inline-flex items-center text-xs uppercase tracking-wider2 text-navy border border-navy/20 px-3 py-1">
              {item.duration}
            </div>
            <p className="mt-5 text-sm sm:text-base text-ink/75 leading-relaxed">{item.body}</p>
          </article>
        ))}
      </div>

      <p className="mt-10 text-sm text-muted">
        <span className="text-navy font-medium">Total time:</span> 35–45 minutes
      </p>

      <div className="mt-12 bg-mist border-l-2 border-gold p-6 sm:p-7 flex gap-4 items-start">
        <ShieldCheck className="w-5 h-5 text-navy flex-none mt-0.5" strokeWidth={1.75} />
        <p className="text-sm sm:text-[15px] text-ink/80 leading-relaxed">
          <span className="font-medium text-navy">Privacy.</span> Your responses are stored securely and used only for your assessment and authorised review. Sessions are deleted 60&nbsp;days after completion unless flagged for archive.
        </p>
      </div>

      {(err || storeError) && (
        <p className="mt-6 text-sm text-red-700">{err || storeError}</p>
      )}

      <div className="mt-14">
        <button type="button" onClick={onContinue} disabled={busy} className="btn-primary disabled:opacity-60">
          {busy ? 'Loading…' : 'Continue'}
          <ArrowRight className="w-4 h-4" strokeWidth={2} />
        </button>
      </div>
    </section>
  );
}
