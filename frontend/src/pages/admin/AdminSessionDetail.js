import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Download, FileText, FileJson, FileCode, Archive, ArchiveRestore,
  Trash2, RotateCcw, Copy, Check, Clock, AlertTriangle, Mail, Building2, UserSquare2, Calendar,
  FileCheck2, RefreshCw,
} from 'lucide-react';
import {
  getSession, patchSession, softDeleteSession, restoreSession, resynthesize,
  conversationDownloadUrl, deliverableDownloadUrl, apiErrorMessage,
} from '../../lib/adminApi';
import ScoreChip from '../../components/admin/ScoreChip';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'psychometric', label: 'Psychometric' },
  { id: 'ai', label: 'AI Discussion' },
  { id: 'scenario', label: 'Scenario' },
  { id: 'deliverable', label: 'Deliverable' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'notes', label: 'Notes' },
];

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}
function fmtDuration(ms) {
  if (!ms) return '—';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60), r = sec % 60;
  return `${m}m ${r}s`;
}
function copyToClipboard(text) {
  try { navigator.clipboard.writeText(text); return true; } catch { return false; }
}

export default function AdminSessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [copied, setCopied] = useState(false);
  const [notes, setNotes] = useState('');
  const [notesSavedAt, setNotesSavedAt] = useState(null);
  const [notesSaving, setNotesSaving] = useState(false);
  const notesTimer = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await getSession(sessionId);
      setDoc(d);
      setNotes(d.admin_notes || '');
    } catch (e) {
      setError(apiErrorMessage(e, 'Could not load session.'));
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  // Notes debounced auto-save (1s)
  const onNotesChange = (value) => {
    setNotes(value);
    if (notesTimer.current) clearTimeout(notesTimer.current);
    notesTimer.current = setTimeout(async () => {
      setNotesSaving(true);
      try {
        await patchSession(sessionId, { notes: value });
        setNotesSavedAt(new Date());
      } catch (e) {
        setError(apiErrorMessage(e, 'Note save failed.'));
      } finally {
        setNotesSaving(false);
      }
    }, 1000);
  };

  async function onToggleArchive() {
    try { await patchSession(sessionId, { archived: !doc.archived }); await load(); }
    catch (e) { alert(apiErrorMessage(e, 'Action failed.')); }
  }
  async function onSoftDelete() {
    if (!window.confirm('Soft-delete this session? PII will be scrubbed; scores and transcripts remain. Restoration is possible for 30 days.')) return;
    try { await softDeleteSession(sessionId); await load(); }
    catch (e) { alert(apiErrorMessage(e, 'Action failed.')); }
  }
  async function onRestoreSession() {
    try { const r = await restoreSession(sessionId); await load(); alert(`Restored. PII was not recoverable (scrubbed on delete).`); }
    catch (e) { alert(apiErrorMessage(e, 'Restore failed.')); }
  }

  // Hotfix Phase 9 (G6) — admin re-run of synthesis. Discards any current
  // deliverable, runs the synthesis worker again. Polls every 5 s until the
  // synthesis sub-block finishes (status moves out of "in_progress").
  const [resynthBusy, setResynthBusy] = useState(false);
  const [resynthMsg, setResynthMsg] = useState(null);

  async function onResynthesize() {
    if (!window.confirm('This will discard the current deliverable and run synthesis again. Continue?')) return;
    setResynthBusy(true);
    setResynthMsg('Re-running synthesis…');
    try {
      const r = await resynthesize(sessionId);
      // Poll session state every 5s, up to 5 minutes, until synthesis
      // completes or fails.
      const deadline = Date.now() + 5 * 60 * 1000;
      let final = null;
      while (Date.now() < deadline) {
        await new Promise((res) => setTimeout(res, 5000));
        const fresh = await getSession(sessionId);
        const st = fresh?.synthesis?.status;
        if (st === 'completed' || st === 'failed') { final = fresh; break; }
      }
      if (!final) {
        setResynthMsg('Still running after 5 minutes — check back later.');
      } else if (final.synthesis?.status === 'completed') {
        setResynthMsg('Synthesis completed.');
        await load();
      } else {
        setResynthMsg('Synthesis failed: ' + (final.synthesis?.error || 'unknown'));
        await load();
      }
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && detail.reason === 'missing_inputs') {
        setResynthMsg(`Cannot re-run: ${(detail.missing || []).join(', ')} score(s) missing.`);
      } else {
        setResynthMsg(apiErrorMessage(e, 'Re-synthesis failed.'));
      }
    } finally {
      setResynthBusy(false);
    }
  }

  const participant = doc?.participant || {};
  const isRedacted = !!doc?.redacted;
  const hasDeliverable = !!(doc?.deliverable && !doc.deliverable.scoring_error);
  const scoringError = !!(doc?.deliverable && doc.deliverable.scoring_error);

  const categoryColour = hasDeliverable ? (doc.deliverable.executive_summary?.overall_colour || 'gold') : null;
  const category = hasDeliverable ? (doc.deliverable.executive_summary?.overall_category || 'n/a') : null;

  if (loading) {
    return <p className="text-sm uppercase tracking-wider2 text-muted">Loading session…</p>;
  }
  if (error || !doc) {
    return (
      <div>
        <p className="text-sm text-terracotta">{error || 'Session not found.'}</p>
        <Link to="/admin/sessions" className="mt-4 inline-block btn-ghost"><ArrowLeft className="w-4 h-4" /> Back to sessions</Link>
      </div>
    );
  }

  return (
    <section>
      {/* Ribbon */}
      <div className="bg-navy text-white p-6 mb-6 relative">
        <Link to="/admin/sessions" className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-wider2 text-white/70 hover:text-gold">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to sessions
        </Link>
        <div className="mt-3 flex items-start justify-between gap-6 flex-wrap">
          <div>
            <span className="inline-block text-[10px] uppercase tracking-wider2 text-gold">Session detail</span>
            <h1 className="mt-1 font-serif text-3xl leading-tight">
              {isRedacted ? <span className="italic text-white/70">(redacted)</span> : (participant.name || 'Untitled')}
            </h1>
            <div className="mt-2 text-sm text-white/70 flex flex-wrap items-center gap-x-5 gap-y-1">
              {participant.organisation && <span className="inline-flex items-center gap-1.5"><Building2 className="w-3.5 h-3.5" />{participant.organisation}</span>}
              {participant.role && <span className="inline-flex items-center gap-1.5"><UserSquare2 className="w-3.5 h-3.5" />{participant.role}</span>}
              {participant.email && !isRedacted && <span className="inline-flex items-center gap-1.5"><Mail className="w-3.5 h-3.5" />{participant.email}</span>}
            </div>
            <div className="mt-3 flex items-center gap-2.5 text-[10px] flex-wrap">
              <span className="inline-flex items-center gap-1 font-mono text-white/80">{sessionId.slice(0, 8)}…
                <button type="button" className="text-white/60 hover:text-gold" onClick={() => { if (copyToClipboard(sessionId)) { setCopied(true); setTimeout(() => setCopied(false), 1200); } }}>
                  {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              </span>
              <ScoreChip colour={categoryColour} size="sm">{category || 'n/a'}</ScoreChip>
              <span className="bg-white/10 px-2 py-0.5 uppercase tracking-wider2 text-[10px]">{doc.stage || 'unknown'}</span>
              {doc.archived && <span className="bg-gold text-navy px-2 py-0.5 uppercase tracking-wider2 text-[10px]">Archived</span>}
              {doc.deleted_at && <span className="bg-terracotta text-white px-2 py-0.5 uppercase tracking-wider2 text-[10px]">Soft-deleted</span>}
            </div>
          </div>

          {/* Action rail */}
          <div className="flex flex-wrap items-center gap-2">
            {hasDeliverable && (
              <>
                <a href={deliverableDownloadUrl(sessionId, 'pdf')} className="inline-flex items-center gap-1.5 px-3 py-2 bg-gold text-navy text-xs uppercase tracking-wider2 font-medium hover:bg-gold-light">
                  <Download className="w-3.5 h-3.5" /> PDF
                </a>
                <a href={deliverableDownloadUrl(sessionId, 'markdown')} className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-white text-xs uppercase tracking-wider2 hover:bg-white/20">
                  <FileText className="w-3.5 h-3.5" /> MD
                </a>
              </>
            )}
            <a href={conversationDownloadUrl(sessionId, 'markdown')} className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-white text-xs uppercase tracking-wider2 hover:bg-white/20">
              <FileCode className="w-3.5 h-3.5" /> Convo MD
            </a>
            <a href={conversationDownloadUrl(sessionId, 'json')} className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-white text-xs uppercase tracking-wider2 hover:bg-white/20">
              <FileJson className="w-3.5 h-3.5" /> Convo JSON
            </a>
            <button
              type="button"
              onClick={onResynthesize}
              disabled={resynthBusy}
              className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-white text-xs uppercase tracking-wider2 hover:bg-gold hover:text-navy disabled:opacity-50"
              aria-label="Re-run synthesis on this session"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${resynthBusy ? 'animate-spin' : ''}`} /> {resynthBusy ? 'Re-running…' : 'Re-run synthesis'}
            </button>
            <button type="button" onClick={onToggleArchive} className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-white text-xs uppercase tracking-wider2 hover:bg-white/20">
              {doc.archived ? <><ArchiveRestore className="w-3.5 h-3.5" /> Unarchive</> : <><Archive className="w-3.5 h-3.5" /> Archive</>}
            </button>
            {!doc.deleted_at && (
              <button type="button" onClick={onSoftDelete} className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-white text-xs uppercase tracking-wider2 hover:bg-terracotta">
                <Trash2 className="w-3.5 h-3.5" /> Soft delete
              </button>
            )}
            {doc.deleted_at && (
              <button type="button" onClick={onRestoreSession} className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-white text-xs uppercase tracking-wider2 hover:bg-gold hover:text-navy">
                <RotateCcw className="w-3.5 h-3.5" /> Restore
              </button>
            )}
          </div>
        </div>

        {/* Lifecycle strip */}
        <div className="mt-5 pt-4 border-t border-white/10 grid grid-cols-2 md:grid-cols-4 gap-4 text-[11px]">
          <Kv icon={Calendar} label="Created" value={fmtDate(doc.created_at)} />
          <Kv icon={Clock} label="Started" value={fmtDate(doc.started_at)} />
          <Kv icon={FileCheck2} label="Completed" value={fmtDate(doc.completed_at)} />
          <Kv icon={Clock} label={doc.archived ? 'Archived (no expiry)' : (doc.hard_delete_at ? 'Hard delete at' : 'Expires at')}
              value={doc.archived ? '—' : (doc.hard_delete_at ? fmtDate(doc.hard_delete_at) : fmtDate(doc.expires_at))} />
        </div>
      </div>

      {scoringError && (
        <div className="mb-5 card-gold-top flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-terracotta mt-0.5" strokeWidth={2} />
          <div className="text-sm">
            <strong className="text-navy">Scoring error persisted.</strong>
            <p className="text-muted mt-1">{(doc.deliverable._error) || 'The LLM synthesis did not produce a valid deliverable.'}</p>
          </div>
        </div>
      )}

      {resynthMsg && (
        <div className="mb-5 card-gold-top flex items-start gap-3">
          <RefreshCw className={`w-4 h-4 text-navy mt-0.5 ${resynthBusy ? 'animate-spin' : ''}`} strokeWidth={2} />
          <div className="text-sm">
            <strong className="text-navy">Re-run synthesis</strong>
            <p className="text-muted mt-1">{resynthMsg}</p>
          </div>
          {!resynthBusy && (
            <button type="button" onClick={() => setResynthMsg(null)} className="ml-auto text-xs uppercase tracking-wider2 text-muted hover:text-navy">
              Dismiss
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      <div role="tablist" aria-label="Session sections" className="border-b border-hairline mb-6 overflow-x-auto">
        <div className="flex items-center gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={activeTab === t.id}
              aria-controls={`panel-${t.id}`}
              onClick={() => setActiveTab(t.id)}
              className={
                'px-4 py-2.5 text-xs uppercase tracking-wider2 border-b-2 transition-colors ' +
                (activeTab === t.id ? 'border-gold text-navy font-semibold' : 'border-transparent text-muted hover:text-navy')
              }
            >{t.label}</button>
          ))}
        </div>
      </div>

      <div>
        {activeTab === 'overview' && <OverviewTab doc={doc} />}
        {activeTab === 'psychometric' && <PsychometricTab doc={doc} />}
        {activeTab === 'ai' && <AIDiscussionTab doc={doc} />}
        {activeTab === 'scenario' && <ScenarioTab doc={doc} />}
        {activeTab === 'deliverable' && <DeliverableTab doc={doc} />}
        {activeTab === 'timeline' && <TimelineTab doc={doc} />}
        {activeTab === 'notes' && (
          <NotesTab
            value={notes}
            onChange={onNotesChange}
            savedAt={notesSavedAt}
            saving={notesSaving}
          />
        )}
      </div>
    </section>
  );
}

function Kv({ icon: Icon, label, value }) {
  return (
    <div>
      <p className="text-white/50 uppercase tracking-wider2 flex items-center gap-1"><Icon className="w-3 h-3" />{label}</p>
      <p className="mt-1 text-white/90">{value}</p>
    </div>
  );
}

// -------- Overview Tab -------- //
function OverviewTab({ doc }) {
  const deliverable = doc.deliverable || {};
  const es = deliverable.executive_summary || {};
  const profiles = deliverable.dimension_profiles || [];
  const sa = useMemo(() => {
    const scores = doc.scores || {};
    const claimed = scores.psychometric?.self_awareness_claimed?.mean_1_5;
    const cu = scores.ai_fluency?.components?.capability_understanding?.score;
    const bs = (scores.ai_fluency?.blind_spots || []).length;
    if (claimed == null || cu == null) return null;
    const proxy = Math.max(1, Math.min(5, 5 - 0.5 * bs));
    const observed = 0.5 * cu + 0.5 * proxy;
    const delta = Math.round((claimed - observed) * 100) / 100;
    const abs = Math.abs(delta);
    const band = abs < 0.5 ? 'Well-calibrated' : abs <= 1.0 ? 'Slightly miscalibrated' : 'Significantly miscalibrated';
    const dir = delta > 0 ? 'over-claiming' : delta < 0 ? 'under-claiming' : 'aligned';
    return { claimed: Math.round(claimed * 100) / 100, observed: Math.round(observed * 100) / 100, delta, band, dir };
  }, [doc]);

  return (
    <div id="panel-overview" role="tabpanel" className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div className="lg:col-span-2 bg-white border border-hairline p-6">
        <h2 className="eyebrow text-navy">Executive summary</h2>
        {es.prose ? (
          <>
            <p className="mt-4 text-[15px] text-ink/85 leading-relaxed">{es.prose}</p>
            {es.bottom_line && <p className="mt-4 text-sm italic text-navy/80">{es.bottom_line}</p>}
          </>
        ) : (
          <p className="mt-4 text-sm text-muted italic">Synthesis not yet produced for this session.</p>
        )}
      </div>
      <div className="bg-white border border-hairline p-6">
        <h2 className="eyebrow text-navy">Dimension radar</h2>
        <RadarChart profiles={profiles} />
      </div>
      {sa && (
        <div className="lg:col-span-3 bg-white border border-hairline p-6">
          <h2 className="eyebrow text-navy">Self-awareness calibration</h2>
          <p className="mt-2 text-sm">
            <span className="font-medium text-navy">{sa.band}</span>
            <span className="text-muted"> · Δ = {sa.delta} ({sa.dir})</span>
          </p>
          <div className="mt-3 relative h-2 bg-hairline">
            <div className="absolute -top-1 h-4 w-1 bg-navy" style={{ left: `${(Math.max(-2, Math.min(2, sa.delta)) + 2) * 25}%` }} />
          </div>
          <div className="mt-2 flex justify-between text-[10px] uppercase tracking-wider2 text-muted">
            <span>Under-claiming</span><span>Well-calibrated</span><span>Over-claiming</span>
          </div>
          <p className="mt-3 text-xs text-ink/70">
            <span className="text-navy font-medium">Claimed:</span> {sa.claimed}
            <span className="mx-3">·</span>
            <span className="text-navy font-medium">Observed:</span> {sa.observed}
          </p>
        </div>
      )}
    </div>
  );
}

function RadarChart({ profiles }) {
  const size = 220, cx = size / 2, cy = size / 2, r = 82;
  // Fixed dimension order for the axes
  const order = ['learning_agility', 'tolerance_for_ambiguity', 'cognitive_flexibility',
                 'self_awareness_accuracy', 'ai_fluency', 'systems_thinking'];
  const scores = Object.fromEntries((profiles || []).map((p) => [p.dimension_id, p.score]));
  const axes = order.map((id, i) => {
    const angle = (-Math.PI / 2) + (i / order.length) * Math.PI * 2;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    const score = scores[id] ?? 0;
    const sx = cx + (score / 5) * r * Math.cos(angle);
    const sy = cy + (score / 5) * r * Math.sin(angle);
    const labelX = cx + (r + 14) * Math.cos(angle);
    const labelY = cy + (r + 14) * Math.sin(angle);
    return { id, x, y, sx, sy, labelX, labelY, score, angle };
  });
  const polyPoints = axes.map((a) => `${a.sx},${a.sy}`).join(' ');

  return (
    <div className="flex items-center justify-center">
      <svg width={size + 60} height={size + 30} viewBox={`-30 0 ${size + 60} ${size + 30}`} role="img" aria-label="Dimension radar">
        {[0.25, 0.5, 0.75, 1.0].map((scale, i) => (
          <polygon
            key={i}
            points={axes.map((a) => `${cx + scale * r * Math.cos(a.angle)},${cy + scale * r * Math.sin(a.angle)}`).join(' ')}
            fill="none"
            stroke="#1e3a5f"
            strokeOpacity={0.1}
          />
        ))}
        {axes.map((a) => <line key={a.id} x1={cx} y1={cy} x2={a.x} y2={a.y} stroke="#1e3a5f" strokeOpacity={0.15} />)}
        <polygon points={polyPoints} fill="#1e3a5f" fillOpacity={0.28} stroke="#1e3a5f" strokeWidth={1.5} />
        {axes.map((a) => (
          <text key={a.id + '-l'} x={a.labelX} y={a.labelY} fontSize="8.5" fill="#6b7280"
                textAnchor={Math.cos(a.angle) > 0.1 ? 'start' : Math.cos(a.angle) < -0.1 ? 'end' : 'middle'}
                dominantBaseline="middle" letterSpacing="1" style={{ textTransform: 'uppercase' }}>
            {a.id.replace(/_/g, ' ').slice(0, 12)}
          </text>
        ))}
      </svg>
    </div>
  );
}

// -------- Psychometric Tab -------- //
function PsychometricTab({ doc }) {
  const scores = doc.scores?.psychometric || {};
  const la = scores.learning_agility || {};
  const ta = scores.tolerance_for_ambiguity || {};
  const answers = doc.answers || [];
  const [sortBy, setSortBy] = useState('order');

  const sorted = useMemo(() => {
    const arr = [...answers];
    if (sortBy === 'rt') arr.sort((a, b) => (b.response_time_ms || 0) - (a.response_time_ms || 0));
    else arr.sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
    return arr;
  }, [answers, sortBy]);

  return (
    <div id="panel-psychometric" className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ScoreCard title="Learning Agility" mean={la.mean_1_5} band={la.band} subscales={la.subscales} />
        <ScoreCard title="Tolerance for Ambiguity" mean={ta.mean_1_5} band={ta.band} subscales={ta.subscales} />
      </div>
      <div className="bg-white border border-hairline p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="eyebrow text-navy">All 20 responses</h2>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="form-input py-1.5 text-xs max-w-[180px]">
            <option value="order">Sort: position</option>
            <option value="rt">Sort: response time (desc)</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider2 text-muted border-b border-hairline">
                <th className="text-left px-3 py-2">#</th>
                <th className="text-left px-3 py-2">Scale</th>
                <th className="text-left px-3 py-2">Subscale</th>
                <th className="text-left px-3 py-2">Value (1–6)</th>
                <th className="text-left px-3 py-2">Response time</th>
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 && <tr><td colSpan={5} className="px-3 py-5 text-muted italic text-sm">No responses on file.</td></tr>}
              {sorted.map((a, i) => (
                <tr key={a.item_id || i} className="border-b border-hairline">
                  <td className="px-3 py-2 text-ink/70">{(a.position ?? i) + 1}</td>
                  <td className="px-3 py-2 text-ink/80">{a.scale || '—'}</td>
                  <td className="px-3 py-2 text-ink/80">{a.subscale || '—'}</td>
                  <td className="px-3 py-2 text-navy font-medium">{a.value ?? '—'}</td>
                  <td className="px-3 py-2 text-ink/80">{fmtDuration(a.response_time_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ScoreCard({ title, mean, band, subscales }) {
  return (
    <div className="bg-white border border-hairline p-5">
      <h3 className="eyebrow text-navy">{title}</h3>
      <p className="mt-2 text-3xl font-serif text-navy">{mean != null ? Number(mean).toFixed(2) : '—'}<span className="text-sm text-muted">/5</span></p>
      {band && <p className="text-xs uppercase tracking-wider2 text-gold-dark">{band}</p>}
      {subscales && (
        <div className="mt-4 space-y-2">
          {Object.entries(subscales).map(([k, v]) => (
            <div key={k}>
              <div className="flex items-baseline justify-between text-xs">
                <span className="text-ink/80 capitalize">{k.replace(/_/g, ' ')}</span>
                <span className="text-muted">{v?.mean_1_5 != null ? Number(v.mean_1_5).toFixed(2) : '—'}</span>
              </div>
              <div className="h-1.5 bg-hairline mt-1">
                <div className="h-1.5 bg-navy/60" style={{ width: `${((v?.mean_1_5 || 0) / 5) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// -------- AI Discussion Tab -------- //
function AIDiscussionTab({ doc }) {
  const [showJson, setShowJson] = useState(false);
  const convo = doc.conversation || [];
  const af = doc.scores?.ai_fluency || {};
  return (
    <div id="panel-ai" className="space-y-6">
      <div className="bg-white border border-hairline p-5">
        <h2 className="eyebrow text-navy">Conversation ({convo.filter(t => t.role === 'user').length} user turns)</h2>
        <div className="mt-4 space-y-4">
          {convo.length === 0 && <p className="text-sm text-muted italic">No conversation on record.</p>}
          {convo.map((t, i) => (
            <div key={i} className={'p-4 border ' + (t.role === 'assistant' ? 'border-hairline bg-mist' : 'border-navy/10 bg-white')}>
              <div className="flex items-center justify-between mb-2 text-[11px] uppercase tracking-wider2">
                <span className={t.role === 'assistant' ? 'text-gold-dark font-medium' : 'text-navy font-medium'}>
                  {t.role === 'assistant' ? 'Interviewer' : t.role === 'user' ? 'Participant' : t.role}
                </span>
                <span className="text-muted">{t.timestamp ? fmtDate(t.timestamp) : ''}</span>
              </div>
              <p className="text-[14px] text-ink/85 leading-relaxed whitespace-pre-wrap">{t.content}</p>
              {t.role === 'assistant' && (t.provider || t.model || t.latency_ms != null) && (
                <div className="mt-2 text-[10px] uppercase tracking-wider2 text-muted/70 font-mono">
                  {t.provider && <span className="mr-3">provider={t.provider}</span>}
                  {t.model && <span className="mr-3">model={t.model}</span>}
                  {t.latency_ms != null && <span className="mr-3">latency={t.latency_ms}ms</span>}
                  {t.fallbacks_tried != null && <span>fallbacks={t.fallbacks_tried}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white border border-hairline p-5">
        <button type="button" onClick={() => setShowJson((s) => !s)} className="text-xs uppercase tracking-wider2 text-navy hover:text-gold">
          {showJson ? '▼' : '▶'} Scoring JSON (scores.ai_fluency)
        </button>
        {showJson && (
          <pre className="mt-3 text-[11px] font-mono bg-mist p-4 overflow-x-auto max-h-[500px]">
{JSON.stringify(af, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

// -------- Scenario Tab -------- //
function ScenarioTab({ doc }) {
  const scn = doc.scenario || {};
  const scores = doc.scores?.scenario || {};
  const p1 = scn.part1_response || {};
  const p2 = scn.part2_response || {};
  return (
    <div id="panel-scenario" className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white border border-hairline p-5">
          <h2 className="eyebrow text-navy">Part 1 responses</h2>
          <dl className="mt-3 space-y-3 text-sm">
            {['q1', 'q2', 'q3'].map((k) => (
              <div key={k}>
                <dt className="text-[10px] uppercase tracking-wider2 text-muted">{k}</dt>
                <dd className="mt-1 text-ink/85 whitespace-pre-wrap">{p1[k] || <em className="text-muted">—</em>}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="bg-white border border-hairline p-5">
          <h2 className="eyebrow text-navy">Part 2 responses (post-curveball)</h2>
          <dl className="mt-3 space-y-3 text-sm">
            {['q1', 'q2', 'q3'].map((k) => (
              <div key={k}>
                <dt className="text-[10px] uppercase tracking-wider2 text-muted">{k}</dt>
                <dd className="mt-1 text-ink/85 whitespace-pre-wrap">{p2[k] || <em className="text-muted">—</em>}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {scores.cognitive_flexibility && (
        <div className="bg-white border border-hairline p-5">
          <h2 className="eyebrow text-navy">Cognitive Flexibility — {scores.cognitive_flexibility.score}/5</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div><dt className="inline text-navy font-medium">Part 1 position. </dt><dd className="inline">{scores.cognitive_flexibility.evidence?.part1_position}</dd></div>
            <div><dt className="inline text-navy font-medium">Part 2 revision. </dt><dd className="inline">{scores.cognitive_flexibility.evidence?.part2_revision}</dd></div>
            <div><dt className="inline text-navy font-medium">Revision quality. </dt><dd className="inline">{scores.cognitive_flexibility.evidence?.revision_quality}</dd></div>
          </dl>
          {scores.cognitive_flexibility.evidence?.key_quote && (
            <p className="mt-3 border-l-2 border-gold pl-4 italic text-ink/75">"{scores.cognitive_flexibility.evidence.key_quote}"</p>
          )}
        </div>
      )}

      {scores.systems_thinking && (
        <div className="bg-white border border-hairline p-5">
          <h2 className="eyebrow text-navy">Systems Thinking — {scores.systems_thinking.score}/5</h2>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider2 text-muted mb-1">Identified</p>
              <ul className="list-disc ml-4 space-y-1 text-sm text-ink/85">
                {(scores.systems_thinking.evidence?.connections_identified || []).map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider2 text-muted mb-1">Missed</p>
              <ul className="list-disc ml-4 space-y-1 text-sm text-ink/85">
                {(scores.systems_thinking.evidence?.connections_missed || []).map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          </div>
          {scores.systems_thinking.evidence?.key_quote && (
            <p className="mt-3 border-l-2 border-gold pl-4 italic text-ink/75">"{scores.systems_thinking.evidence.key_quote}"</p>
          )}
        </div>
      )}
    </div>
  );
}

// -------- Deliverable Tab -------- //
function DeliverableTab({ doc }) {
  const d = doc.deliverable || {};
  const es = d.executive_summary || {};
  const profiles = d.dimension_profiles || [];
  const dd = d.ai_fluency_deep_dive || {};
  const ia = d.integration_analysis || {};
  const recs = d.development_recommendations || [];

  if (!d || Object.keys(d).length === 0 || d.scoring_error) {
    return (
      <div className="bg-white border border-hairline p-6 text-sm text-muted">
        <AlertTriangle className="inline w-4 h-4 text-terracotta mr-1" />
        No deliverable available for this session{d.scoring_error ? ' (scoring error).' : ' yet.'}
      </div>
    );
  }

  return (
    <div id="panel-deliverable" className="space-y-8 max-w-[820px] mx-auto">
      <section>
        <div className="flex items-center gap-3 flex-wrap">
          <ScoreChip colour={es.overall_colour}>{es.overall_category}</ScoreChip>
          <span className="text-sm text-ink/70">{es.category_statement}</span>
        </div>
        <h2 className="mt-4 font-serif text-2xl text-navy">Executive Summary</h2>
        <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">{es.prose}</p>
        <p className="mt-3 italic text-navy/80">{es.bottom_line}</p>
      </section>
      <section>
        <h2 className="font-serif text-2xl text-navy">Dimension Profiles</h2>
        <div className="mt-4 space-y-5">
          {profiles.map((p) => (
            <div key={p.dimension_id} className="border-t border-hairline pt-4">
              <h3 className="font-serif text-lg text-navy">
                {p.name || p.dimension_id} <span className="text-sm font-sans text-muted"> · {p.score}/5 · {p.confidence}</span>
                <span className="ml-3"><ScoreChip colour={p.band?.colour} size="sm">{p.band?.category}</ScoreChip></span>
              </h3>
              <p className="mt-2 text-[14px] text-ink/80 leading-relaxed">{p.observed}</p>
              {(p.evidence_quotes || []).length > 0 && (
                <ul className="mt-2 space-y-1 border-l-2 border-gold pl-3">
                  {p.evidence_quotes.map((q, i) => <li key={i} className="text-[13px] italic text-ink/70">"{q}"</li>)}
                </ul>
              )}
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2 className="font-serif text-2xl text-navy">AI Fluency Deep Dive</h2>
        <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">{dd.overview}</p>
        <table className="mt-4 w-full text-sm">
          <thead><tr className="bg-mist text-left text-[10px] uppercase tracking-wider2 text-navy">
            <th className="px-3 py-2">Component</th><th className="px-3 py-2">Score</th><th className="px-3 py-2">Conf</th><th className="px-3 py-2">Notes</th>
          </tr></thead>
          <tbody>
            {(dd.components_table || []).map((r, i) => (
              <tr key={i} className="border-b border-hairline">
                <td className="px-3 py-2 text-navy font-medium">{r.component}</td>
                <td className="px-3 py-2">{r.score}/5</td>
                <td className="px-3 py-2 capitalize">{r.confidence}</td>
                <td className="px-3 py-2 text-ink/75">{r.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2 className="font-serif text-2xl text-navy">Development Recommendations</h2>
        <div className="mt-3 space-y-4">
          {recs.map((r, i) => (
            <article key={i}>
              <h3 className="font-serif text-lg text-navy">{i + 1}. {r.title}</h3>
              <dl className="mt-1 space-y-1 text-sm text-ink/85">
                <div><dt className="inline text-navy font-medium">What: </dt><dd className="inline">{r.what}</dd></div>
                <div><dt className="inline text-navy font-medium">Why: </dt><dd className="inline">{r.why}</dd></div>
                <div><dt className="inline text-navy font-medium">How: </dt><dd className="inline">{r.how}</dd></div>
                <div><dt className="inline text-navy font-medium">Expectation: </dt><dd className="inline">{r.expectation}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>
      <section>
        <h2 className="font-serif text-2xl text-navy">Integration Analysis</h2>
        <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">{ia.patterns}</p>
        {ia.contradictions && <p className="mt-2 text-[15px] text-ink/85"><span className="text-navy font-medium">Contradictions. </span>{ia.contradictions}</p>}
        <p className="mt-2 text-[15px] text-ink/85"><span className="text-navy font-medium">Emergent themes. </span>{ia.emergent_themes}</p>
      </section>
      <section>
        <h2 className="font-serif text-2xl text-navy">Methodology Note</h2>
        <p className="mt-3 text-[14px] text-ink/80 leading-relaxed">{d.methodology_note}</p>
      </section>
    </div>
  );
}

// -------- Timeline Tab -------- //
function TimelineTab({ doc }) {
  const events = useMemo(() => {
    const e = [];
    if (doc.created_at) e.push({ t: doc.created_at, label: 'Session created', hint: `resume code ${doc.resume_code}` });
    if (doc.consent?.accepted_at) e.push({ t: doc.consent.accepted_at, label: 'Consent accepted' });
    if (doc.started_at) e.push({ t: doc.started_at, label: 'Assessment started' });
    (doc.answers || []).forEach((a) => {
      if (a.answered_at) e.push({ t: a.answered_at, label: `Psychometric q${(a.position ?? 0) + 1} = ${a.value}`, hint: `${a.scale}/${a.subscale} · ${fmtDuration(a.response_time_ms)}` });
    });
    if (doc.ai_discussion?.started_at) e.push({ t: doc.ai_discussion.started_at, label: 'AI discussion started' });
    (doc.conversation || []).forEach((t, i) => {
      if (t.timestamp) e.push({ t: t.timestamp, label: `${t.role === 'assistant' ? 'Interviewer' : 'Participant'} turn ${t.turn ?? i}`, hint: (t.content || '').slice(0, 90) });
    });
    if (doc.ai_discussion?.completed_at) e.push({ t: doc.ai_discussion.completed_at, label: 'AI discussion complete' });
    if (doc.scenario?.phase_entered_at) {
      Object.entries(doc.scenario.phase_entered_at).forEach(([phase, ts]) => {
        if (ts) e.push({ t: ts, label: `Scenario → ${phase}` });
      });
    }
    if (doc.scenario?.completed_at) e.push({ t: doc.scenario.completed_at, label: 'Scenario complete' });
    if (doc.synthesis?.started_at) e.push({ t: doc.synthesis.started_at, label: 'Synthesis started' });
    if (doc.synthesis?.completed_at) e.push({ t: doc.synthesis.completed_at, label: `Synthesis ${doc.synthesis.status}`, hint: `${doc.synthesis.provider || ''} / ${doc.synthesis.model || ''}` });
    if (doc.completed_at) e.push({ t: doc.completed_at, label: 'Session completed' });
    if (doc.deleted_at) e.push({ t: doc.deleted_at, label: 'Soft-deleted', hint: 'PII scrubbed' });
    if (doc.last_admin_viewed_at) e.push({ t: doc.last_admin_viewed_at, label: 'Last admin view' });
    e.sort((a, b) => (a.t || '').localeCompare(b.t || ''));
    return e;
  }, [doc]);

  return (
    <div id="panel-timeline" className="bg-white border border-hairline p-5">
      <h2 className="eyebrow text-navy">Event timeline</h2>
      <ol className="mt-4 border-l-2 border-hairline ml-2 space-y-4">
        {events.map((e, i) => (
          <li key={i} className="pl-4 relative">
            <span className="absolute -left-[5px] top-1 w-2 h-2 bg-navy rounded-full" />
            <p className="text-[11px] uppercase tracking-wider2 text-muted">{fmtDate(e.t)}</p>
            <p className="text-sm text-navy font-medium">{e.label}</p>
            {e.hint && <p className="text-[12px] text-ink/60 mt-0.5">{e.hint}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

// -------- Notes Tab -------- //
function NotesTab({ value, onChange, savedAt, saving }) {
  return (
    <div id="panel-notes" className="bg-white border border-hairline p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="eyebrow text-navy">Admin notes</h2>
        <p className="text-[11px] text-muted">
          {saving ? 'Saving…' : (savedAt ? `Saved ${savedAt.toLocaleTimeString()}` : 'Auto-saved as you type')}
        </p>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, 2000))}
        placeholder="Private notes for assessors — maximum 2,000 characters."
        className="form-input min-h-[260px] font-mono text-[13px]"
      />
      <p className="mt-2 text-[11px] text-muted">{value.length} / 2,000 characters. Not shown to participants.</p>
    </div>
  );
}
