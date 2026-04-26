import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Send, AlertTriangle, RefreshCw, CheckCircle2 } from 'lucide-react';
import { useSession } from '../../store/sessionStore';
import { aiStart, aiMessage, aiComplete, aiState, aiRetry, apiErrorMessage, apiErrorStatus } from '../../lib/api';

const MAX_USER_TURNS = 12;
const MAX_CHARS = 2000;

export default function AIDiscussion() {
  const navigate = useNavigate();
  const sessionId = useSession((s) => s.sessionId);
  const advanceStage = useSession((s) => s.advanceStage);
  const currentStage = useSession((s) => s.stage);

  const [phase, setPhase] = useState('loading'); // loading | intro | chat | done
  const [messages, setMessages] = useState([]);
  const [turnCount, setTurnCount] = useState(0);
  const [canSubmit, setCanSubmit] = useState(false);
  const [atCap, setAtCap] = useState(false);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState(null);
  const [retryBanner, setRetryBanner] = useState(false);
  const [confirmingEnd, setConfirmingEnd] = useState(false);
  const [continuing, setContinuing] = useState(false);

  const transcriptRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight + 400;
    }
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  // Defensive redirect
  useEffect(() => {
    if (!sessionId) return;
    if (currentStage && ['scenario', 'processing', 'results'].includes(currentStage)) {
      navigate(`/assessment/${currentStage}`, { replace: true });
    }
  }, [sessionId, currentStage, navigate]);

  // On mount: load state
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await aiState(sessionId);
        if (cancelled) return;
        if (s.status === 'completed') {
          setPhase('done');
          setMessages(s.messages || []);
          setTurnCount(s.user_turn_count || 0);
          return;
        }
        if (s.status === 'in_progress') {
          // Resume — skip intro
          setMessages(s.messages || []);
          setTurnCount(s.user_turn_count || 0);
          setCanSubmit(Boolean(s.can_submit));
          setAtCap(Boolean(s.at_cap));
          setPhase('chat');
          return;
        }
        // Not yet started
        setPhase('intro');
      } catch (e) {
        setErr(apiErrorMessage(e, 'Could not load the discussion state.'));
        setPhase('intro');
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  useEffect(() => {
    // Auto-scroll when new message arrives
    scrollToBottom();
  }, [messages.length, thinking, scrollToBottom]);

  async function onBegin() {
    if (!sessionId) return;
    setThinking(true);
    setErr(null);
    try {
      const s = await aiStart(sessionId);
      setMessages(s.messages || []);
      setTurnCount(s.user_turn_count || 0);
      setCanSubmit(Boolean(s.can_submit));
      setAtCap(Boolean(s.at_cap));
      setPhase(s.status === 'completed' ? 'done' : 'chat');
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not start the discussion.'));
    } finally {
      setThinking(false);
    }
  }

  async function onSend() {
    const content = input.trim();
    if (!content || !canSubmit || sending) return;
    if (content.length > MAX_CHARS) {
      setErr(`Please keep responses under ${MAX_CHARS} characters.`);
      return;
    }
    setErr(null);
    setRetryBanner(false);
    setSending(true);
    // Optimistically append user turn (no turn number — server will reconcile)
    const optimistic = { turn: turnCount + 1, role: 'user', content, timestamp: new Date().toISOString(), _optimistic: true };
    setMessages((m) => [...m, optimistic]);
    setInput('');
    setCanSubmit(false);
    setThinking(true);
    try {
      const s = await aiMessage(sessionId, content);
      setMessages(s.messages || []);
      setTurnCount(s.user_turn_count || 0);
      setCanSubmit(Boolean(s.can_submit));
      setAtCap(Boolean(s.at_cap));
      if (s.status === 'completed') {
        setPhase('done');
      }
    } catch (e) {
      const status = apiErrorStatus(e);
      // Rollback optimistic on non-server-side errors (422) so user can edit and retry
      if (status === 503) {
        setRetryBanner(true);
        // Keep the optimistic user message so they can see what they sent; /retry will carry on
      } else {
        // Rollback optimistic
        setMessages((m) => m.filter((x) => !x._optimistic));
        setInput(content);
        setCanSubmit(true);
        setErr(apiErrorMessage(e, 'Could not send your message.'));
      }
    } finally {
      setSending(false);
      setThinking(false);
    }
  }

  async function onRetry() {
    if (!sessionId || sending) return;
    setSending(true);
    setThinking(true);
    setErr(null);
    try {
      const s = await aiRetry(sessionId);
      setMessages(s.messages || []);
      setTurnCount(s.user_turn_count || 0);
      setCanSubmit(Boolean(s.can_submit));
      setAtCap(Boolean(s.at_cap));
      setRetryBanner(false);
      if (s.status === 'completed') {
        setPhase('done');
      }
    } catch (e) {
      setErr(apiErrorMessage(e, 'Still cannot reach the model.'));
    } finally {
      setSending(false);
      setThinking(false);
    }
  }

  async function onEndEarly() {
    if (!sessionId) return;
    setThinking(true);
    setErr(null);
    try {
      await aiComplete(sessionId);
      const s = await aiState(sessionId);
      setMessages(s.messages || []);
      setTurnCount(s.user_turn_count || 0);
      setPhase('done');
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not end the discussion.'));
    } finally {
      setThinking(false);
      setConfirmingEnd(false);
    }
  }

  async function onContinue() {
    setContinuing(true);
    try {
      await advanceStage('scenario');
      navigate('/assessment/scenario');
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not continue.'));
    } finally {
      setContinuing(false);
    }
  }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  // ------------------------------- renderers ----------------------------- //
  if (phase === 'loading') {
    return (
      <section className="max-w-3xl">
        <p className="text-sm uppercase tracking-wider2 text-muted">Loading discussion…</p>
      </section>
    );
  }

  if (phase === 'intro') {
    return (
      <section className="max-w-3xl">
        <span className="eyebrow">Stage 2 of 3</span>
        <h1 className="mt-4 text-3xl sm:text-4xl md:text-5xl font-serif text-navy tracking-tight leading-tight">
          AI Fluency Discussion
        </h1>
        <span className="mt-6 gold-rule block" aria-hidden="true" />
        <p className="mt-8 text-base sm:text-lg text-ink/80 leading-relaxed">
          A short conversation about your understanding and use of AI. The interviewer will adapt its
          questions to your responses.
        </p>
        <p className="mt-5 text-sm text-muted leading-relaxed">
          Around 10–12 exchanges (5–10 minutes). Answer as you would in a real leadership conversation
          — there is no right answer.
        </p>
        {err && <p className="mt-4 text-sm text-red-700">{err}</p>}
        <div className="mt-10">
          <button type="button" onClick={onBegin} disabled={thinking || !sessionId} className="btn-primary disabled:opacity-60">
            {thinking ? 'Starting…' : 'Begin conversation'}
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
          AI Fluency Discussion complete
        </h1>
        <span className="mt-6 gold-rule block" aria-hidden="true" />
        <p className="mt-8 text-base sm:text-lg text-ink/80 leading-relaxed">
          Thank you. Next, a short strategic scenario.
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

  // phase === 'chat'
  const composerDisabled = sending || !canSubmit || phase !== 'chat';
  const charsUsed = input.length;

  return (
    <section className="max-w-3xl">
      {/* Header strip */}
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <span className="eyebrow">AI Fluency Discussion</span>
        <span className="text-xs uppercase tracking-wider2 text-muted">
          Turn <span className="text-navy font-medium">{turnCount}</span> of{' '}
          <span className="text-navy font-medium">{MAX_USER_TURNS}</span>
        </span>
      </div>

      {retryBanner && (
        <div className="mt-4 flex items-start gap-3 border border-hairline bg-mist p-4">
          <AlertTriangle className="w-4 h-4 text-gold flex-none mt-0.5" strokeWidth={2} />
          <div className="flex-1">
            <p className="text-sm text-ink/80">
              We couldn&rsquo;t reach the model. Your message is saved — you can retry now.
            </p>
            <button type="button" onClick={onRetry} disabled={sending} className="mt-2 inline-flex items-center gap-2 text-xs uppercase tracking-wider2 text-navy font-medium hover:text-navy-dark">
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          </div>
        </div>
      )}

      {/* Transcript */}
      <div
        ref={transcriptRef}
        className="mt-8"
        aria-live="polite"
        aria-label="AI Fluency Discussion transcript"
      >
        <ul className="space-y-7">
          {messages.map((m, i) => (
            <li key={`${m.turn}-${m.role}-${i}`} className={'flex ' + (m.role === 'user' ? 'justify-end' : 'justify-start')}>
              {m.role === 'assistant' ? (
                <div className="flex items-start gap-3 max-w-[85%]">
                  <span className="flex-none w-8 h-8 rounded-full border border-navy flex items-center justify-center text-navy font-serif text-xs tracking-wider">AI</span>
                  <div className="text-ink/90 font-sans leading-relaxed whitespace-pre-wrap text-[15px]">
                    {m.content}
                  </div>
                </div>
              ) : (
                <div className="max-w-[85%] border-r-2 border-gold pr-4 pl-5 py-1 text-ink/90 whitespace-pre-wrap text-[15px] leading-relaxed">
                  {m.content}
                </div>
              )}
            </li>
          ))}
          {thinking && (
            <li className="flex justify-start">
              <div className="flex items-center gap-3">
                <span className="flex-none w-8 h-8 rounded-full border border-navy flex items-center justify-center text-navy font-serif text-xs tracking-wider">AI</span>
                <span className="italic text-navy text-sm">Considering your response…</span>
              </div>
            </li>
          )}
        </ul>
      </div>

      {/* Composer */}
      {!atCap && (
        <div className="mt-10 border-t border-hairline pt-6">
          <label className="block" htmlFor="ai-composer">
            <span className="sr-only">Your response</span>
            <textarea
              id="ai-composer"
              aria-label="Your response"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              disabled={composerDisabled}
              rows={3}
              maxLength={MAX_CHARS}
              placeholder="Type your response…"
              className="w-full bg-white border border-hairline px-4 py-3 text-[15px] text-ink font-sans leading-relaxed focus:border-navy focus:outline-none disabled:opacity-60 min-h-[90px] resize-y"
            />
          </label>
          <div className="mt-3 flex items-center justify-between flex-wrap gap-3">
            <span className="text-[11px] uppercase tracking-wider2 text-muted">
              Enter sends — Shift+Enter for newline
              {charsUsed > MAX_CHARS - 200 && (
                <span className="ml-2 text-gold">{charsUsed}/{MAX_CHARS}</span>
              )}
            </span>
            <div className="flex items-center gap-4">
              {turnCount >= 3 && !atCap && (
                <button type="button" onClick={() => setConfirmingEnd(true)} className="btn-ghost">
                  End conversation
                </button>
              )}
              <button type="button" onClick={onSend} disabled={composerDisabled || !input.trim()} className="btn-primary disabled:opacity-60">
                {sending ? 'Sending…' : 'Send'}
                <Send className="w-4 h-4" strokeWidth={2} />
              </button>
            </div>
          </div>
        </div>
      )}

      {err && <p className="mt-5 text-sm text-red-700">{err}</p>}

      {/* End confirmation modal — copy branches by turn count */}
      {confirmingEnd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="Close"
            tabIndex={-1}
            className="absolute inset-0 bg-navy-deep/60"
            onClick={() => setConfirmingEnd(false)}
          />
          <div className="relative bg-white border border-hairline p-7 max-w-md w-full">
            {turnCount >= MAX_USER_TURNS - 2 ? (
              // Wrap-up framing — turns 10 or 11. The model is instructed by
              // Doc 21 to start wrapping up around turn 10, so the assistant
              // tone has shifted to closing language. Don't frame this as
              // "early" — it's natural completion.
              <>
                <h2 className="font-serif text-xl text-navy">Ready to wrap up?</h2>
                <p className="mt-3 text-sm text-ink/75 leading-relaxed">
                  It looks like the conversation has reached a natural close.
                  Continuing will move you to the strategic scenario.
                </p>
                <div className="mt-6 flex items-center justify-end gap-3">
                  <button type="button" className="btn-ghost" onClick={() => setConfirmingEnd(false)}>Keep going</button>
                  <button type="button" className="btn-primary" onClick={onEndEarly}>Continue to scenario</button>
                </div>
              </>
            ) : (
              // Early-exit framing — turns 3..9. The participant is bailing
              // before the conversation has had time to develop fully.
              <>
                <h2 className="font-serif text-xl text-navy">End the conversation now?</h2>
                <p className="mt-3 text-sm text-ink/75 leading-relaxed">
                  You&rsquo;ve completed {turnCount} of {MAX_USER_TURNS} exchanges. We&rsquo;ll close
                  the discussion and move on to the strategic scenario.
                </p>
                <div className="mt-6 flex items-center justify-end gap-3">
                  <button type="button" className="btn-ghost" onClick={() => setConfirmingEnd(false)}>Keep going</button>
                  <button type="button" className="btn-primary" onClick={onEndEarly}>End conversation</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
