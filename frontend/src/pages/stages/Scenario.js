import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ArrowLeft, CheckCircle2, Loader2 } from 'lucide-react';
import { useSession } from '../../store/sessionStore';
import {
  scnState, scnStart, scnAdvance, scnAutosave,
  apiErrorMessage, apiErrorStatus,
  API_BASE,
} from '../../lib/api';
import { registerFlusher } from '../../lib/flushRegistry';
import CountdownTimer from '../../components/CountdownTimer';

const PHASE_LABELS = {
  read: 'Read the scenario',
  part1: 'Your response — Part 1',
  curveball: 'New information',
  part2: 'Your response — Part 2',
  done: 'Complete',
};

const MAX_CHARS = 4000;

export default function Scenario() {
  const navigate = useNavigate();
  const sessionId = useSession((s) => s.sessionId);
  const advanceStage = useSession((s) => s.advanceStage);
  const currentStage = useSession((s) => s.stage);

  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState(null); // 'read' | 'part1' | 'curveball' | 'part2' | 'done' | null
  const [content, setContent] = useState(null);
  const [part1, setPart1] = useState({ q1: '', q2: '', q3: '' });
  const [part2, setPart2] = useState({ q1: '', q2: '', q3: '' });
  const [savedAt, setSavedAt] = useState(null);
  const [saving, setSaving] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [err, setErr] = useState(null);
  const [continuing, setContinuing] = useState(false);

  // Defensive redirect
  useEffect(() => {
    if (!sessionId) return;
    if (currentStage === 'processing' || currentStage === 'results') {
      navigate(`/assessment/${currentStage}`, { replace: true });
    }
  }, [sessionId, currentStage, navigate]);

  // Initial load
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await scnState(sessionId);
        if (cancelled) return;
        if (!st.status) {
          // start the scenario right away
          const started = await scnStart(sessionId);
          setPhase(started.phase);
          setContent(started.content || null);
          setPart1({ q1: '', q2: '', q3: '', ...(started.part1_response || {}) });
          setPart2({ q1: '', q2: '', q3: '', ...(started.part2_response || {}) });
        } else {
          setPhase(st.phase);
          setContent(st.content || null);
          setPart1({ q1: '', q2: '', q3: '', ...(st.part1_response || {}) });
          setPart2({ q1: '', q2: '', q3: '', ...(st.part2_response || {}) });
          if (st.status === 'completed') {
            // If server says processing/results, redirect happens elsewhere; otherwise show done panel.
            setPhase('done');
          }
        }
      } catch (e) {
        setErr(apiErrorMessage(e, 'Could not load scenario.'));
      } finally {
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  // Debounced autosave helpers
  const autosaveTimerRef = useRef(null);

  // Refs that always hold the latest values for the flusher / page-close
  // listener. These are updated on every state change so the flush-on-exit
  // path never sees stale closures.
  const sessionIdRef = useRef(sessionId);
  const phaseRef = useRef(phase);
  const part1Ref = useRef(part1);
  const part2Ref = useRef(part2);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);
  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { part1Ref.current = part1; }, [part1]);
  useEffect(() => { part2Ref.current = part2; }, [part2]);

  // Explicit flush — cancels any pending debounce and POSTs the full trio
  // for the current writing phase. Used by SaveExit, Continue, and unmount.
  // Never throws: exit flows must never be blocked by a network failure.
  const flushNow = useCallback(async () => {
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
    const sid = sessionIdRef.current;
    const ph = phaseRef.current;
    if (!sid) return;
    if (ph !== 'part1' && ph !== 'part2') return;
    const trio = ph === 'part1' ? part1Ref.current : part2Ref.current;
    const partial = {
      q1: typeof trio.q1 === 'string' ? trio.q1 : '',
      q2: typeof trio.q2 === 'string' ? trio.q2 : '',
      q3: typeof trio.q3 === 'string' ? trio.q3 : '',
    };
    try {
      const r = await scnAutosave(sid, ph, partial);
      setSavedAt(r.saved_at);
    } catch (_) {
      // Silent — never block navigation on autosave failure.
    }
  }, []);

  // Register the flusher so SaveExitModal can await it before navigating away.
  useEffect(() => {
    const unregister = registerFlusher(flushNow);
    return () => {
      // On unmount, cancel any debounce and unregister. We intentionally do
      // NOT await an unmount-time network call here because React unmount
      // cannot await; Save & exit handles the awaited flush path. The
      // pagehide/visibilitychange beacon below handles browser-close.
      if (autosaveTimerRef.current) {
        clearTimeout(autosaveTimerRef.current);
        autosaveTimerRef.current = null;
      }
      unregister();
    };
  }, [flushNow]);

  // Browser-close / tab-hide path — Hotfix Phase 9 (G2). Always send the
  // FULL current trio for the active phase as the autosave body. Prefer
  // navigator.sendBeacon (purpose-built to survive unload) with a Blob of
  // application/json; fall back to fetch keepalive:true if Beacon is
  // unavailable. Body is verified non-empty before firing.
  useEffect(() => {
    function beacon() {
      const sid = sessionIdRef.current;
      const ph = phaseRef.current;
      if (!sid) return;
      if (ph !== 'part1' && ph !== 'part2') return;
      const trio = ph === 'part1' ? part1Ref.current : part2Ref.current;
      const partial = {
        q1: typeof trio.q1 === 'string' ? trio.q1 : '',
        q2: typeof trio.q2 === 'string' ? trio.q2 : '',
        q3: typeof trio.q3 === 'string' ? trio.q3 : '',
      };
      const bodyStr = JSON.stringify({ session_id: sid, phase: ph, partial });
      if (!bodyStr || bodyStr.length < 20) return; // never fire an empty/garbled body
      const url = `${API_BASE}/assessment/scenario/autosave`;
      try {
        if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
          const blob = new Blob([bodyStr], { type: 'application/json' });
          const queued = navigator.sendBeacon(url, blob);
          if (queued) return;
        }
        // Fallback — fetch with keepalive:true.
        fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: bodyStr,
          keepalive: true,
        }).catch(() => {});
      } catch (_) {
        // ignore — best-effort
      }
    }
    function onVis() {
      if (document.visibilityState === 'hidden') beacon();
    }
    window.addEventListener('pagehide', beacon);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.removeEventListener('pagehide', beacon);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  // Hotfix Phase 9 (G2) — full-trio snapshot autosave on a 400 ms debounce.
  // Previous behaviour ("partial-merge per keystroke") could lose content if
  // the user typed continuously across fields without 400 ms pauses; we now
  // always send all three current values for the active phase, so server
  // state always mirrors what's on screen.
  const queueAutosave = useCallback((thisPhase) => {
    if (!sessionIdRef.current) return;
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(async () => {
      const sid = sessionIdRef.current;
      const ph = thisPhase || phaseRef.current;
      if (!sid || (ph !== 'part1' && ph !== 'part2')) return;
      const trio = ph === 'part1' ? part1Ref.current : part2Ref.current;
      const snapshot = {
        q1: typeof trio.q1 === 'string' ? trio.q1 : '',
        q2: typeof trio.q2 === 'string' ? trio.q2 : '',
        q3: typeof trio.q3 === 'string' ? trio.q3 : '',
      };
      setSaving(true);
      try {
        const r = await scnAutosave(sid, ph, snapshot);
        setSavedAt(r.saved_at);
      } catch (_) {
        // Swallow — typing should not be blocked.
      } finally {
        setSaving(false);
      }
    }, 400);
  }, []);

  function updatePart1(k, v) {
    setPart1((prev) => {
      const next = { ...prev, [k]: v };
      part1Ref.current = next;       // keep ref live for the snapshot in queueAutosave
      queueAutosave('part1');
      return next;
    });
  }
  function updatePart2(k, v) {
    setPart2((prev) => {
      const next = { ...prev, [k]: v };
      part2Ref.current = next;
      queueAutosave('part2');
      return next;
    });
  }

  async function goForward() {
    setAdvancing(true);
    setErr(null);
    try {
      if (phase === 'read') {
        const r = await scnAdvance(sessionId, 'read', 'part1');
        setPhase(r.phase);
        setContent(r.content);
      } else if (phase === 'part1') {
        const r = await scnAdvance(sessionId, 'part1', 'curveball', part1);
        setPhase(r.phase);
        setContent(r.content);
      } else if (phase === 'curveball') {
        const r = await scnAdvance(sessionId, 'curveball', 'part2');
        setPhase(r.phase);
        setContent(r.content);
      } else if (phase === 'part2') {
        // Scoring will run server-side; this can take 10–30s
        setScoring(true);
        const r = await scnAdvance(sessionId, 'part2', 'done', part2);
        setPhase(r.phase || 'done');
        setContent({});
      }
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not advance.'));
    } finally {
      setAdvancing(false);
      setScoring(false);
    }
  }

  async function onContinue() {
    setContinuing(true);
    try {
      await advanceStage('processing');
      navigate('/assessment/processing');
    } catch (e) {
      // Server already advanced stage to 'processing' on part2 submission; local store might not reflect that.
      // Navigate anyway.
      navigate('/assessment/processing');
    } finally {
      setContinuing(false);
    }
  }

  const canContinuePart1 = useMemo(
    () => (part1.q1 || '').trim() && (part1.q2 || '').trim() && (part1.q3 || '').trim(),
    [part1],
  );
  const canContinuePart2 = useMemo(
    () => (part2.q1 || '').trim() && (part2.q2 || '').trim() && (part2.q3 || '').trim(),
    [part2],
  );

  // --------- render ----------
  if (loading) return <p className="text-sm uppercase tracking-wider2 text-muted">Loading scenario…</p>;
  if (!phase) return <p className="text-sm uppercase tracking-wider2 text-muted">No scenario state.</p>;

  if (scoring) {
    return (
      <section className="max-w-3xl">
        <div className="card card-gold-top">
          <div className="flex items-center gap-3">
            <Loader2 className="w-5 h-5 animate-spin text-navy" strokeWidth={2} />
            <p className="text-sm uppercase tracking-wider2 text-navy">Analysing your response…</p>
          </div>
          <p className="mt-4 italic text-ink/70 leading-relaxed">This takes up to 30 seconds.</p>
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
          Strategic scenario complete
        </h1>
        <span className="mt-6 gold-rule block" aria-hidden="true" />
        <p className="mt-8 text-base sm:text-lg text-ink/80 leading-relaxed">
          Next, we&rsquo;ll synthesise your results across the six dimensions.
        </p>
        {err && <p className="mt-4 text-sm text-red-700">{err}</p>}
        <div className="mt-10">
          <button type="button" onClick={onContinue} disabled={continuing} className="btn-primary disabled:opacity-60">
            {continuing ? 'Continuing…' : 'Continue'}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>
      </section>
    );
  }

  const targetMin = content && content.duration_target_minutes;

  return (
    <section className="max-w-3xl">
      {/* Header strip with timer */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <span className="eyebrow">Strategic Scenario</span>
          <h1 className="mt-3 text-2xl sm:text-3xl font-serif text-navy tracking-tight leading-tight">
            {PHASE_LABELS[phase]}
          </h1>
        </div>
        {targetMin ? (
          <CountdownTimer targetMinutes={targetMin} label={PHASE_LABELS[phase]} startKey={phase} />
        ) : null}
      </div>
      <span className="mt-5 gold-rule block" aria-hidden="true" />

      {phase === 'read' && <ReadPhase content={content} />}
      {phase === 'part1' && (
        <AnswerPhase
          kind="part1"
          content={content}
          values={part1}
          onChange={updatePart1}
          saving={saving}
          savedAt={savedAt}
        />
      )}
      {phase === 'curveball' && <CurveballPhase content={content} />}
      {phase === 'part2' && (
        <AnswerPhase
          kind="part2"
          content={content}
          values={part2}
          onChange={updatePart2}
          saving={saving}
          savedAt={savedAt}
        />
      )}

      {err && <p className="mt-6 text-sm text-red-700">{err}</p>}

      <div className="mt-12 flex items-center justify-end gap-4">
        {phase === 'read' && (
          <button type="button" onClick={goForward} disabled={advancing} className="btn-primary disabled:opacity-60">
            {advancing ? 'Loading…' : 'Begin Part 1'}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
        {phase === 'part1' && (
          <button type="button" onClick={goForward} disabled={!canContinuePart1 || advancing} className="btn-primary disabled:opacity-60">
            {advancing ? 'Loading…' : 'Continue to new information'}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
        {phase === 'curveball' && (
          <button type="button" onClick={goForward} disabled={advancing} className="btn-primary disabled:opacity-60">
            {advancing ? 'Loading…' : 'Continue to Part 2'}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
        {phase === 'part2' && (
          <button type="button" onClick={goForward} disabled={!canContinuePart2 || advancing} className="btn-primary disabled:opacity-60">
            {advancing ? 'Submitting…' : 'Submit final response'}
            <ArrowRight className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
      </div>
    </section>
  );
}

function ReadPhase({ content }) {
  if (!content) return null;
  return (
    <div className="mt-10">
      <h2 className="font-serif text-2xl text-navy">{content.title}</h2>
      {(content.body_sections || []).map((sec, idx) => (
        <div key={idx} className="mt-8">
          {sec.heading && (
            <h3 className="font-serif text-lg text-navy mb-3">{sec.heading}</h3>
          )}
          <ul className="space-y-2">
            {(sec.lines || []).map((l, j) => (
              <li key={j} className={l.type === 'bullet' ? 'list-disc ml-5 text-ink/85 leading-relaxed' : 'text-ink/85 leading-relaxed'}>
                {l.text}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function AnswerPhase({ kind, content, values, onChange, saving, savedAt }) {
  if (!content) return null;
  const questions = content.questions || [];
  const preamble = content.preamble;
  const postamble = content.postamble;

  return (
    <div className="mt-10">
      {preamble && <p className="text-ink/80 leading-relaxed">{preamble}</p>}
      {questions.map((q, i) => (
        <QuestionBlock
          key={i}
          kind={kind}
          values={values}
          onChange={onChange}
          index={i}
          text={q}
        />
      ))}
      {postamble && (
        <p className="mt-6 text-xs uppercase tracking-wider2 text-muted">{postamble}</p>
      )}
      <div className="mt-4 h-4 text-[11px] uppercase tracking-wider2" aria-live="polite">
        {saving ? (
          <span className="text-muted">Saving…</span>
        ) : savedAt ? (
          <SavedAgo timestamp={savedAt} />
        ) : null}
      </div>
    </div>
  );
}

// Module-scope component. Previously declared INSIDE AnswerPhase, which gave
// it a fresh function identity on every parent render — React unmounted and
// remounted each <textarea>, dropping focus on every keystroke (a textbook
// anti-pattern). Hoisted here so the textarea instance is stable across the
// 400 ms autosave-driven re-renders introduced in the Phase 9 hotfix (G2).
function QuestionBlock({ kind, values, onChange, index, text }) {
  const key = `q${index + 1}`;
  const id = `${kind}-${key}`;
  const value = values[key] || '';
  const charsLeft = MAX_CHARS - value.length;
  return (
    <div className="mt-8">
      <label htmlFor={id} className="block">
        <span className="font-serif text-lg text-navy leading-snug" id={`${id}-label`}>
          <span className="text-gold mr-2">{index + 1}.</span>{text}
        </span>
      </label>
      <textarea
        id={id}
        aria-labelledby={`${id}-label`}
        className="mt-3 w-full bg-white border border-hairline px-4 py-3 text-[15px] text-ink font-sans leading-relaxed focus:border-navy focus:outline-none min-h-[150px] resize-y"
        rows={6}
        maxLength={MAX_CHARS}
        value={value}
        onChange={(e) => onChange(key, e.target.value)}
      />
      <div className="mt-1 text-[10px] uppercase tracking-wider2 text-muted text-right">
        {charsLeft < 300 && (
          <span className={charsLeft < 0 ? 'text-red-700' : 'text-gold'}>
            {value.length}/{MAX_CHARS}
          </span>
        )}
      </div>
    </div>
  );
}

// Hotfix Phase 9 (G2) — live relative timestamp so the participant has visible
// confirmation that their typing is reaching the server. Updates every 2s.
function SavedAgo({ timestamp }) {
  const [, setTick] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 2000);
    return () => clearInterval(id);
  }, []);
  const sec = Math.max(0, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000));
  const label = sec < 5
    ? 'Saved just now'
    : sec < 60
      ? `Saved ${sec}s ago`
      : sec < 3600
        ? `Saved ${Math.floor(sec / 60)}m ago`
        : `Saved at ${new Date(timestamp).toLocaleTimeString()}`;
  return <span className="text-gold-dark">{label}</span>;
}

function CurveballPhase({ content }) {
  if (!content) return null;
  return (
    <div className="mt-10">
      <p className="text-ink/80 leading-relaxed">
        Three new pieces of information have arrived. Consider them, then move to your updated response.
      </p>
      <p className="mt-4 text-ink/80 leading-relaxed italic">{content.preamble}</p>
      <ol className="mt-6 space-y-6">
        {(content.items || []).map((it) => (
          <li key={it.number} className="card card-gold-top">
            <p className="eyebrow">Item {it.number}</p>
            <h3 className="mt-2 font-serif text-lg text-navy">{it.heading}</h3>
            <p className="mt-3 text-ink/85 leading-relaxed whitespace-pre-wrap">{it.body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
