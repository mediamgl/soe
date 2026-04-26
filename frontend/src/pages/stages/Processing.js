import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, RefreshCcw, AlertTriangle, ArrowLeftCircle } from 'lucide-react';
import { useSession } from '../../store/sessionStore';
import { processingStart, processingState, apiErrorMessage } from '../../lib/api';

const MIN_DISPLAY_MS = 8000;
const POLL_MS = 3000;
const SLOW_HELPER_AFTER_MS = 90000;
// Hotfix Phase 9 (G1) — escape panel after this much wall-clock time on the
// Processing screen with no transition. Matches the backend total-synthesis
// budget (TOTAL_SYNTHESIS_BUDGET_SEC=240) so we never strand a participant
// after the server has decided synthesis won't complete.
const ESCAPE_AFTER_MS = 240000;

const STATUS_LINES = [
  'Synthesising psychometric signal…',
  'Reviewing your AI fluency discussion…',
  'Mapping strategic-scenario responses…',
  'Composing your profile…',
];

// Stages we know how to bounce a stuck participant back to.
const STAGE_ROUTES = {
  identity: '/start',
  context: '/context',
  psychometric: '/assessment/psychometric',
  'ai-discussion': '/assessment/ai-discussion',
  scenario: '/assessment/scenario',
  processing: '/assessment/processing',
  results: '/assessment/results',
};

export default function Processing() {
  const navigate = useNavigate();
  const sessionId = useSession((s) => s.sessionId);
  const stage = useSession((s) => s.stage);
  const advanceStage = useSession((s) => s.advanceStage);

  const [status, setStatus] = useState(null); // null | 'in_progress' | 'completed' | 'failed' | 'escape'
  const [escapeReason, setEscapeReason] = useState(null); // null | 'stage_mismatch' | 'timeout' | 'error'
  const [error, setError] = useState(null);
  const [startedMountAt] = useState(() => Date.now());
  const [statusIdx, setStatusIdx] = useState(0);
  const [slowHelper, setSlowHelper] = useState(false);
  const [readyToContinue, setReadyToContinue] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [bouncingHome, setBouncingHome] = useState(false);

  const pollRef = useRef(null);
  const statusLineRef = useRef(null);
  const slowRef = useRef(null);
  const escapeRef = useRef(null);
  const mountedRef = useRef(true);

  // Rotate the status line every 3s
  useEffect(() => {
    statusLineRef.current = setInterval(() => {
      setStatusIdx((i) => (i + 1) % STATUS_LINES.length);
    }, 3000);
    return () => clearInterval(statusLineRef.current);
  }, []);

  // 90 s slow-helper line (kept from Phase 7)
  useEffect(() => {
    slowRef.current = setTimeout(() => setSlowHelper(true), SLOW_HELPER_AFTER_MS);
    return () => clearTimeout(slowRef.current);
  }, []);

  // Hotfix Phase 9 (G1) — 240 s escape-panel timer.
  useEffect(() => {
    escapeRef.current = setTimeout(() => {
      if (!mountedRef.current) return;
      setStatus((cur) => {
        // If we already left the loading state, leave it alone.
        if (cur === 'completed' || cur === 'failed' || cur === 'escape') return cur;
        setEscapeReason('timeout');
        return 'escape';
      });
    }, ESCAPE_AFTER_MS);
    return () => clearTimeout(escapeRef.current);
  }, []);

  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; }; }, []);

  // Boot: GET state; if null → POST start. Poll every 3 s.
  useEffect(() => {
    if (!sessionId) return;
    let stop = false;

    async function bootAndPoll() {
      try {
        const st = await processingState(sessionId);
        if (stop) return;
        if (!st.status) {
          try {
            await processingStart(sessionId);
            setStatus('in_progress');
          } catch (startErr) {
            // Hotfix Phase 9 (G1) — surface the gate failures explicitly so
            // the participant gets the escape panel immediately rather than
            // spinning indefinitely on a false-loading screen.
            const detail = startErr?.response?.data?.detail;
            const reason = (detail && typeof detail === 'object') ? detail.reason : null;
            if (reason === 'stage_mismatch' || reason === 'missing_inputs') {
              setEscapeReason('stage_mismatch');
              setStatus('escape');
              return;
            }
            // Some other error — start the escape grace window but allow Retry.
            setEscapeReason('error');
            setStatus('escape');
            setError(apiErrorMessage(startErr, 'Could not start synthesis.'));
            return;
          }
        } else {
          setStatus(st.status);
        }
      } catch (e) {
        setError(apiErrorMessage(e, 'Could not start synthesis.'));
      }

      // Poll until completed or failed
      pollRef.current = setInterval(async () => {
        if (stop) return;
        try {
          const st = await processingState(sessionId);
          if (stop) return;
          setStatus((cur) => (cur === 'escape' ? cur : st.status));
          if (st.error) setError(st.error);
          if (st.status === 'completed' || st.status === 'failed') {
            clearInterval(pollRef.current);
          }
        } catch (e) {
          // transient — keep polling, surface the last message
          setError(apiErrorMessage(e, 'Polling failed; retrying…'));
        }
      }, POLL_MS);
    }

    bootAndPoll();
    return () => {
      stop = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [sessionId]);

  // Respect minimum floor before revealing Continue
  useEffect(() => {
    if (status === 'completed') {
      const elapsed = Date.now() - startedMountAt;
      const wait = Math.max(0, MIN_DISPLAY_MS - elapsed);
      const t = setTimeout(() => {
        if (mountedRef.current) setReadyToContinue(true);
      }, wait);
      return () => clearTimeout(t);
    }
  }, [status, startedMountAt]);

  async function onRetry() {
    setRetrying(true);
    setError(null);
    try {
      await processingStart(sessionId);
      setStatus('in_progress');
      setEscapeReason(null);
      setSlowHelper(false);
      // Reset the 240 s escape timer for the retry window.
      if (escapeRef.current) clearTimeout(escapeRef.current);
      escapeRef.current = setTimeout(() => {
        if (mountedRef.current) {
          setEscapeReason('timeout');
          setStatus('escape');
        }
      }, ESCAPE_AFTER_MS);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const reason = (detail && typeof detail === 'object') ? detail.reason : null;
      if (reason === 'stage_mismatch' || reason === 'missing_inputs') {
        setEscapeReason('stage_mismatch');
        setStatus('escape');
      } else {
        setError(apiErrorMessage(e, 'Could not restart synthesis.'));
      }
    } finally {
      setRetrying(false);
    }
  }

  async function onBackToAssessment() {
    setBouncingHome(true);
    // Resolve the stage we should bounce to. Prefer the in-store stage; if
    // it's "processing" itself we fall back to "scenario" (synthesis can
    // only start once the scenario is complete).
    const target = (() => {
      const s = (stage || '').toLowerCase();
      if (s && s !== 'processing' && STAGE_ROUTES[s]) return STAGE_ROUTES[s];
      return STAGE_ROUTES.scenario;
    })();
    navigate(target, { replace: true });
  }

  async function onContinue() {
    try {
      await advanceStage('results').catch(() => {});
    } finally {
      navigate('/assessment/results');
    }
  }

  const escapeCopy = useMemo(() => {
    if (escapeReason === 'stage_mismatch') {
      return {
        heading: 'It looks like there are still steps left in your assessment',
        body: 'Your responses are saved. Pick up where you left off and we’ll generate your report when you finish the remaining steps.',
        showRetry: false,
      };
    }
    return {
      heading: 'We’re having trouble completing this step',
      body: 'Your responses are saved. You can come back to your assessment, or try once more.',
      showRetry: true,
    };
  }, [escapeReason]);

  return (
    <section className="max-w-2xl mx-auto">
      <div className="flex flex-col items-center text-center">
        {status !== 'escape' && <PentagonAnimation />}

        <div aria-live="polite" className="mt-10 min-h-[1.5rem]">
          {status === 'escape' ? null : status === 'failed' ? (
            <p className="text-sm text-red-700 italic font-serif">We couldn’t complete the synthesis.</p>
          ) : readyToContinue ? (
            <p className="text-sm uppercase tracking-wider2 text-gold-dark">Your results are ready.</p>
          ) : (
            <p className="text-base italic font-serif text-navy/80">
              {STATUS_LINES[statusIdx]}
            </p>
          )}
        </div>

        {slowHelper && status === 'in_progress' && (
          <p className="mt-6 text-xs uppercase tracking-wider2 text-muted">
            This is taking a little longer than usual…
          </p>
        )}

        {error && status !== 'completed' && status !== 'escape' && (
          <p className="mt-6 text-xs text-red-700 max-w-md">{error}</p>
        )}

        {/* Phase 9 G1 — escape panel */}
        {status === 'escape' && (
          <div className="card card-gold-top mt-2 max-w-xl text-left">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-navy" strokeWidth={1.75} aria-hidden="true" />
              <span className="eyebrow">Action needed</span>
            </div>
            <h2 className="mt-3 font-serif text-2xl text-navy">{escapeCopy.heading}</h2>
            <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">{escapeCopy.body}</p>
            {error && <p className="mt-3 text-xs text-muted">{error}</p>}
            <div className="mt-6 flex flex-wrap gap-3">
              <button type="button" onClick={onBackToAssessment} disabled={bouncingHome} className="btn-primary disabled:opacity-60">
                <ArrowLeftCircle className="w-4 h-4" strokeWidth={2} />
                Back to your assessment
              </button>
              {escapeCopy.showRetry && (
                <button type="button" onClick={onRetry} disabled={retrying} className="btn-ghost disabled:opacity-60">
                  <RefreshCcw className={`w-4 h-4 ${retrying ? 'animate-spin' : ''}`} strokeWidth={2} />
                  Try again
                </button>
              )}
            </div>
          </div>
        )}

        {status === 'failed' && (
          <div className="mt-10">
            <button type="button" onClick={onRetry} disabled={retrying} className="btn-primary disabled:opacity-60">
              {retrying ? 'Restarting…' : 'Retry synthesis'}
              <RefreshCcw className="w-4 h-4" strokeWidth={2} />
            </button>
          </div>
        )}

        {readyToContinue && status === 'completed' && (
          <div className="mt-10">
            <button type="button" onClick={onContinue} className="btn-primary">
              Continue
              <ArrowRight className="w-4 h-4" strokeWidth={2} />
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

// Pentagon SVG with 5 axes that fill in gold one-by-one on a ~10s loop.
function PentagonAnimation() {
  const cx = 120;
  const cy = 120;
  const r = 100;
  const verts = useMemo(() => {
    return Array.from({ length: 5 }, (_, i) => {
      const theta = (-90 + i * 72) * (Math.PI / 180);
      return { x: cx + r * Math.cos(theta), y: cy + r * Math.sin(theta) };
    });
  }, []);
  const polyPoints = verts.map((v) => `${v.x},${v.y}`).join(' ');

  return (
    <div className="relative">
      <svg width="240" height="240" viewBox="0 0 240 240" role="img" aria-label="Synthesising assessment profile">
        {[0.33, 0.66, 1.0].map((s, i) => (
          <polygon
            key={i}
            points={verts.map((v) => `${cx + (v.x - cx) * s},${cy + (v.y - cy) * s}`).join(' ')}
            fill="none"
            stroke="#1e3a5f"
            strokeOpacity={0.12}
            strokeWidth="1"
          />
        ))}
        {verts.map((v, i) => (
          <line
            key={i}
            x1={cx} y1={cy} x2={v.x} y2={v.y}
            stroke="#d4a84b"
            strokeWidth="2.5"
            strokeLinecap="round"
            style={{
              strokeDasharray: r,
              strokeDashoffset: r,
              animation: `tra-axis-fill 10s linear ${i * 1.6}s infinite`,
            }}
          />
        ))}
        <polygon
          points={polyPoints}
          fill="none"
          stroke="#1e3a5f"
          strokeWidth="1.25"
          strokeOpacity={0.75}
        />
        <circle cx={cx} cy={cy} r="3" fill="#1e3a5f" />
      </svg>
      <style>{`
        @keyframes tra-axis-fill {
          0%   { stroke-dashoffset: ${r}; opacity: 0.2; }
          30%  { stroke-dashoffset: 0;   opacity: 1; }
          60%  { stroke-dashoffset: 0;   opacity: 1; }
          100% { stroke-dashoffset: ${r}; opacity: 0.2; }
        }
      `}</style>
    </div>
  );
}
