import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { useSession } from '../../store/sessionStore';
import { psychNext, psychProgress, psychAnswer, apiErrorMessage, apiErrorStatus } from '../../lib/api';

const LIKERT = [
  { value: 1, label: 'Strongly Disagree' },
  { value: 2, label: 'Disagree' },
  { value: 3, label: 'Slightly Disagree' },
  { value: 4, label: 'Slightly Agree' },
  { value: 5, label: 'Agree' },
  { value: 6, label: 'Strongly Agree' },
];

const AUTO_ADVANCE_MS = 450; // Doc 20: auto-advance after selection (subtle confirmation moment)

export default function Psychometric() {
  const navigate = useNavigate();
  const sessionId = useSession((s) => s.sessionId);
  const advanceStage = useSession((s) => s.advanceStage);
  const currentStage = useSession((s) => s.stage);

  // 'intro' | 'item' | 'done'
  const [phase, setPhase] = useState('intro');
  const [current, setCurrent] = useState(null);
  const [progress, setProgress] = useState({ answered: 0, total: 20, current_index_1based: 1 });
  const [selected, setSelected] = useState(null); // value 1-6 while pending advance
  const [savingState, setSavingState] = useState('idle'); // idle | saving | retrying | done
  const [err, setErr] = useState(null);
  const [starting, setStarting] = useState(false);
  const [completing, setCompleting] = useState(false);

  // Timer state — track pauses when tab hidden > 5s
  const itemStartRef = useRef(null);
  const visibilityPausedAtRef = useRef(null);
  const accumulatedPauseRef = useRef(0);

  const beginTimer = useCallback(() => {
    itemStartRef.current = performance.now();
    accumulatedPauseRef.current = 0;
    visibilityPausedAtRef.current = null;
  }, []);

  const elapsedMs = useCallback(() => {
    if (itemStartRef.current == null) return 0;
    const now = performance.now();
    const raw = now - itemStartRef.current;
    return Math.max(0, Math.round(raw - accumulatedPauseRef.current));
  }, []);

  // Visibility handling — pause timer when hidden > 5s
  useEffect(() => {
    let hideAt = null;
    function onVis() {
      if (document.hidden) {
        hideAt = Date.now();
        visibilityPausedAtRef.current = performance.now();
      } else {
        if (hideAt != null && Date.now() - hideAt > 5000 && visibilityPausedAtRef.current != null) {
          accumulatedPauseRef.current += performance.now() - visibilityPausedAtRef.current;
        }
        visibilityPausedAtRef.current = null;
        hideAt = null;
      }
    }
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  // Defensive redirect: if the server stage is already past psychometric, bounce forward.
  // Also: on mount, if the session already has psychometric progress > 0, skip the intro
  // (a resumer should land directly on their next unanswered item).
  useEffect(() => {
    if (!sessionId) return;
    if (currentStage && ['ai-discussion', 'scenario', 'processing', 'results'].includes(currentStage)) {
      navigate(`/assessment/${currentStage}`, { replace: true });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const prog = await psychProgress(sessionId);
        if (cancelled) return;
        if (prog && prog.answered > 0 && !prog.done) {
          // Resuming mid-flow — skip intro, load the next item.
          setProgress(prog);
          await fetchNext();
        } else if (prog && prog.done) {
          // Already finished — show done panel.
          setProgress(prog);
          setPhase('done');
        }
        // answered === 0 -> leave phase='intro' (default)
      } catch (_) { /* non-fatal — intro will still show */ }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line
  }, [sessionId, currentStage, navigate]);

  async function fetchNext() {
    if (!sessionId) return;
    setErr(null);
    try {
      const data = await psychNext(sessionId);
      if (data.done) {
        setPhase('done');
        setProgress(data.progress);
      } else {
        setCurrent(data.item);
        setProgress(data.progress);
        setSelected(null);
        setSavingState('idle');
        setPhase('item');
        beginTimer();
      }
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not load next item.'));
    }
  }

  async function onBegin() {
    setStarting(true);
    await fetchNext();
    setStarting(false);
  }

  async function submitAnswer(value) {
    if (!current || savingState === 'saving' || savingState === 'retrying') return;
    const rt = elapsedMs();
    setSavingState('saving');
    setErr(null);
    let attempt = 0;
    const maxAttempts = 4;
    while (attempt < maxAttempts) {
      attempt += 1;
      try {
        const data = await psychAnswer(sessionId, current.item_id, value, rt);
        setSavingState('done');
        if (data.done) {
          setPhase('done');
          setProgress(data.progress);
        } else {
          await fetchNext();
        }
        return;
      } catch (e) {
        const status = apiErrorStatus(e);
        if (status === 409) {
          // Either out-of-order or already-answered -> reconcile via /next
          setErr('Re-syncing…');
          await fetchNext();
          return;
        }
        if (attempt >= maxAttempts) {
          setSavingState('idle');
          setErr(apiErrorMessage(e, 'Could not save your answer. Please try again.'));
          return;
        }
        setSavingState('retrying');
        await new Promise((r) => setTimeout(r, 400 * attempt));
      }
    }
  }

  // Select a value — auto-advance after ~450ms
  const select = useCallback((value) => {
    if (savingState === 'saving' || savingState === 'retrying') return;
    setSelected(value);
  }, [savingState]);

  // Debounced auto-advance after selection
  useEffect(() => {
    if (selected == null) return undefined;
    const t = setTimeout(() => submitAnswer(selected), AUTO_ADVANCE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [selected]);

  // Keyboard shortcuts: 1-6 select, Enter = submit selected
  useEffect(() => {
    if (phase !== 'item') return undefined;
    function onKey(e) {
      if (e.target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (e.key >= '1' && e.key <= '6') {
        e.preventDefault();
        select(parseInt(e.key, 10));
      } else if (e.key === 'Enter' && selected != null) {
        e.preventDefault();
        submitAnswer(selected);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        setSelected((s) => (s == null ? 1 : Math.min(6, s + 1)));
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setSelected((s) => (s == null ? 6 : Math.max(1, s - 1)));
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line
  }, [phase, selected]);

  async function onComplete() {
    setCompleting(true);
    try {
      await advanceStage('ai-discussion');
      navigate('/assessment/ai-discussion');
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not continue.'));
    } finally {
      setCompleting(false);
    }
  }

  if (phase === 'intro') {
    return (
      <section className="max-w-3xl">
        <span className="eyebrow">Stage 1 of 3</span>
        <h1 className="mt-4 text-3xl sm:text-4xl md:text-5xl font-serif text-navy tracking-tight leading-tight">
          Psychometric Assessment
        </h1>
        <span className="mt-6 gold-rule block" aria-hidden="true" />
        <p className="mt-8 text-base sm:text-lg text-ink/80 leading-relaxed">
          Twenty short statements. For each, choose the option that best reflects you. There is
          no back button — go with your instinct. This takes about 8–10 minutes.
        </p>
        <p className="mt-5 text-sm text-muted leading-relaxed">
          Tip: the number keys <kbd className="font-mono px-1 border border-hairline">1</kbd>
          {' '}to <kbd className="font-mono px-1 border border-hairline">6</kbd>{' '}
          select directly. Your first instinct is usually the truest answer.
        </p>
        {err && <p className="mt-4 text-sm text-red-700">{err}</p>}
        <div className="mt-10">
          <button type="button" onClick={onBegin} disabled={starting || !sessionId} className="btn-primary disabled:opacity-60">
            {starting ? 'Loading…' : 'Begin'}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>
      </section>
    );
  }

  if (phase === 'done') {
    return (
      <section className="max-w-3xl">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="w-6 h-6 text-gold" strokeWidth={1.8} />
          <span className="eyebrow">Section complete</span>
        </div>
        <h1 className="mt-4 text-3xl sm:text-4xl md:text-5xl font-serif text-navy tracking-tight leading-tight">
          Psychometric assessment complete
        </h1>
        <span className="mt-6 gold-rule block" aria-hidden="true" />
        <p className="mt-8 text-base sm:text-lg text-ink/80 leading-relaxed">
          Thank you. Your next step is the AI Fluency Discussion.
        </p>
        {err && <p className="mt-4 text-sm text-red-700">{err}</p>}
        <div className="mt-10">
          <button type="button" onClick={onComplete} disabled={completing} className="btn-primary disabled:opacity-60">
            {completing ? 'Continuing…' : 'Continue'}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>
      </section>
    );
  }

  // phase === 'item'
  const pct = Math.round((progress.answered / progress.total) * 100);
  const scaleLabel = current && current.scale === 'LA' ? 'Learning Agility' : 'Tolerance for Ambiguity';

  return (
    <section className="max-w-3xl">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <p className="text-xs uppercase tracking-wider2 text-muted">
          Psychometric Assessment — Item{' '}
          <span className="text-navy font-medium">{progress.current_index_1based}</span>{' '}of{' '}
          <span className="text-navy font-medium">{progress.total}</span>
        </p>
        <span className="text-[11px] uppercase tracking-wider2 text-gold">{scaleLabel}</span>
      </div>
      <div className="mt-3 h-[3px] w-full bg-mist" aria-hidden="true">
        <div
          className="h-[3px] bg-navy transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <h2 className="mt-10 text-xl sm:text-2xl md:text-[28px] font-serif text-navy leading-[1.4]">
        {current ? current.text : ' '}
      </h2>

      <div
        className="mt-10 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 sm:gap-4"
        role="radiogroup"
        aria-label={current ? `Response to: ${current.text}` : 'Likert response'}
      >
        {LIKERT.map((l) => {
          const isSel = selected === l.value;
          return (
            <button
              key={l.value}
              type="button"
              role="radio"
              aria-checked={isSel}
              onClick={() => select(l.value)}
              disabled={savingState === 'saving' || savingState === 'retrying'}
              className={
                'group flex flex-col items-center text-center py-5 px-3 border transition-colors duration-150 disabled:cursor-not-allowed ' +
                (isSel
                  ? 'border-navy bg-mist'
                  : 'border-hairline hover:border-gold focus:border-gold')
              }
            >
              <span
                className={
                  'font-serif text-3xl sm:text-4xl leading-none mb-2 ' +
                  (isSel ? 'text-navy' : 'text-muted group-hover:text-navy')
                }
              >
                {l.value}
              </span>
              <span
                className={
                  'text-[11px] sm:text-xs uppercase tracking-wider2 ' +
                  (isSel ? 'text-navy font-semibold' : 'text-muted')
                }
              >
                {l.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Status toast */}
      <div className="mt-6 h-5 text-xs uppercase tracking-wider2" aria-live="polite">
        {savingState === 'saving' && <span className="text-muted">Saving…</span>}
        {savingState === 'retrying' && <span className="text-gold">Couldn&rsquo;t save — retrying…</span>}
        {err && !['saving', 'retrying'].includes(savingState) && (
          <span className="text-red-700 normal-case tracking-normal">{err}</span>
        )}
      </div>
    </section>
  );
}
