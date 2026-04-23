import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useSession, STAGE_PATH } from '../../store/sessionStore';

export default function StagePlaceholder({
  stageKey,
  eyebrow,
  title,
  description,
  prevStage,
  prevPath,
  nextStage,
  nextPath,
  backLabel = 'Back',
  nextLabel = 'Continue',
}) {
  const advanceStage = useSession((s) => s.advanceStage);
  const sessionId = useSession((s) => s.sessionId);
  const [busy, setBusy] = useState(null); // 'back' | 'next' | null
  const [err, setErr] = useState(null);
  const navigate = useNavigate();

  async function move(direction) {
    setBusy(direction);
    setErr(null);
    try {
      if (direction === 'back') {
        if (sessionId && prevStage) {
          await advanceStage(prevStage);
        }
        navigate(prevPath || '/');
      } else {
        if (sessionId && nextStage) {
          await advanceStage(nextStage);
        }
        navigate(nextPath || STAGE_PATH[nextStage] || '/');
      }
    } catch (e) {
      setErr(e.message || 'Could not navigate.');
    } finally {
      setBusy(null);
    }
  }

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

      {err && <p className="mt-6 text-sm text-red-700">{err}</p>}

      <div className="mt-12 flex items-center justify-between gap-4 flex-wrap">
        {prevPath ? (
          <button type="button" onClick={() => move('back')} disabled={busy !== null} className="btn-ghost disabled:opacity-50">
            <ArrowLeft className="w-4 h-4" strokeWidth={2} />
            {backLabel}
          </button>
        ) : (
          <span />
        )}
        {nextPath && (
          <button type="button" onClick={() => move('next')} disabled={busy !== null} className="btn-primary disabled:opacity-60">
            {busy === 'next' ? 'Loading…' : nextLabel}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
      </div>
    </section>
  );
}
