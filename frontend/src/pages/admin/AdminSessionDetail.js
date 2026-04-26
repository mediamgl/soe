import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Download, FileText, FileJson, FileCode, Archive, ArchiveRestore,
  Trash2, RotateCcw, Copy, Check, Clock, AlertTriangle, Mail, Building2, UserSquare2, Calendar,
  FileCheck2, RefreshCw,
} from 'lucide-react';
import {
  getSession, getEngagement, patchSession, softDeleteSession, restoreSession, resynthesize,
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
  const [engagement, setEngagement] = useState(null);
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
      // Phase 11B — engagement analytics, fetched in parallel. Failure is
      // non-fatal: the tabs gracefully fall back to the legacy view if it's
      // null.
      try {
        const eg = await getEngagement(sessionId);
        setEngagement(eg);
      } catch {
        setEngagement(null);
      }
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
        {activeTab === 'psychometric' && <PsychometricTab doc={doc} engagement={engagement?.psychometric} />}
        {activeTab === 'ai' && <AIDiscussionTab doc={doc} engagement={engagement?.ai_discussion} />}
        {activeTab === 'scenario' && <ScenarioTab doc={doc} engagement={engagement?.scenario} />}
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
  // Label radius slightly further out to allow room for text without the polygon clipping it.
  const LABEL_R = r + 18;
  const axes = order.map((id, i) => {
    const angle = (-Math.PI / 2) + (i / order.length) * Math.PI * 2;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    const score = scores[id] ?? 0;
    const sx = cx + (score / 5) * r * Math.cos(angle);
    const sy = cy + (score / 5) * r * Math.sin(angle);
    const labelX = cx + LABEL_R * Math.cos(angle);
    const labelY = cy + LABEL_R * Math.sin(angle);
    // Split each label into up to two lines on whitespace — keeps long
    // names like "TOLERANCE FOR AMBIGUITY" inside the SVG canvas without
    // truncation while still aligning to the perimeter.
    const words = id.replace(/_/g, ' ').split(' ');
    const lines = words.length <= 1
      ? [words[0]]
      : words.length === 2
        ? [words[0], words[1]]
        : [words.slice(0, words.length - 1).join(' '), words[words.length - 1]];
    return { id, x, y, sx, sy, labelX, labelY, score, angle, lines };
  });
  const polyPoints = axes.map((a) => `${a.sx},${a.sy}`).join(' ');

  // SVG canvas widened on all sides so two-line labels fit at any axis.
  // Old: -30 0 280 250  → labels clipped at 'TOLERANCE FO' etc.
  // New: -90 -30 400 280 → ~80px each side + 30px top/bottom of breathing
  // room, sufficient for 'TOLERANCE FOR / AMBIGUITY' wrapped on two lines.
  const VB_X = -90, VB_Y = -30, VB_W = size + 180, VB_H = size + 60;

  return (
    <div className="flex items-center justify-center">
      <svg width="100%" height="auto" viewBox={`${VB_X} ${VB_Y} ${VB_W} ${VB_H}`} role="img" aria-label="Dimension radar" style={{ maxWidth: 380 }}>
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
        {axes.map((a) => {
          // text-anchor switches based on which side of the radar the label
          // sits on, so labels never run off into the chart polygon.
          const anchor = Math.cos(a.angle) > 0.15 ? 'start'
                       : Math.cos(a.angle) < -0.15 ? 'end'
                       : 'middle';
          const lineHeight = 9;
          const startDy = a.lines.length === 2 ? -lineHeight / 2 : 0;
          return (
            <text key={a.id + '-l'} x={a.labelX} y={a.labelY} fontSize="8.5" fill="#6b7280"
                  textAnchor={anchor} dominantBaseline="middle"
                  letterSpacing="1" style={{ textTransform: 'uppercase' }}>
              {a.lines.map((line, idx) => (
                <tspan key={idx} x={a.labelX} dy={idx === 0 ? startDy : lineHeight}>{line}</tspan>
              ))}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

// -------- Psychometric Tab -------- //
// Phase 11B — palette for response_time_band → heatmap cell colour.
const RT_BAND_COLOURS = {
  fast:        { bg: '#cfd8e3', fg: '#1e3a5f', label: 'Fast' },
  normal:      { bg: '#1e3a5f', fg: '#ffffff', label: 'Normal' },
  slow:        { bg: '#d4a84b', fg: '#1e3a5f', label: 'Slow' },
  deliberated: { bg: '#b94c3a', fg: '#ffffff', label: 'Deliberated' },
};
function fmtSec(ms) {
  if (ms === null || ms === undefined) return '—';
  const s = Math.round(ms / 100) / 10;  // 1 decimal sec
  return `${s.toFixed(1)}s`;
}

function PsychometricTab({ doc, engagement }) {
  const scores = doc.scores?.psychometric || {};
  const la = scores.learning_agility || {};
  const ta = scores.tolerance_for_ambiguity || {};
  const items = engagement?.items || [];
  const summary = engagement?.summary || null;
  const [sortBy, setSortBy] = useState('order');   // 'order' | 'rt_asc' | 'rt_desc'

  const sortedItems = useMemo(() => {
    if (sortBy === 'rt_desc') return [...items].sort((a, b) => (b.response_time_ms || 0) - (a.response_time_ms || 0));
    if (sortBy === 'rt_asc')  return [...items].sort((a, b) => (a.response_time_ms || 0) - (b.response_time_ms || 0));
    return items;
  }, [items, sortBy]);

  const fastest3 = (summary?.fastest_3 || []).map((id) => items.find((x) => x.item_id === id)).filter(Boolean);
  const slowest3 = (summary?.slowest_3 || []).map((id) => items.find((x) => x.item_id === id)).filter(Boolean);

  return (
    <div id="panel-psychometric" className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ScoreCard title="Learning Agility" mean={la.mean_1_5} band={la.band} subscales={la.subscales} />
        <ScoreCard title="Tolerance for Ambiguity" mean={ta.mean_1_5} band={ta.band} subscales={ta.subscales} />
      </div>

      {/* ---- Phase 11B: engagement summary strip + heatmap ---- */}
      {summary && items.length > 0 && (
        <div className="bg-white border border-hairline border-t-[3px] border-t-gold p-5">
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
            <h2 className="eyebrow text-navy mr-2">Response engagement</h2>
            <span><strong className="text-navy">Median:</strong> {fmtSec(summary.median_ms)}</span>
            <span className="text-muted">25th–75th: {fmtSec(summary.p25_ms)}–{fmtSec(summary.p75_ms)}</span>
            <span><strong className="text-terracotta">{summary.deliberated_count}</strong> item{summary.deliberated_count === 1 ? '' : 's'} deliberated</span>
          </div>

          <ResponseTimeHeatmap items={items} />

          {/* Legend */}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-wider2">
            {Object.entries(RT_BAND_COLOURS).map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <span className="inline-block w-3 h-3" style={{ background: v.bg }} aria-hidden="true" />
                <span className="text-muted">{v.label}</span>
              </span>
            ))}
            <span className="ml-auto text-muted normal-case tracking-normal italic">
              Bands relative to participant's own median ({fmtSec(summary.median_ms)})
            </span>
          </div>

          {/* Fastest + Slowest lists */}
          <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <h3 className="eyebrow text-navy mb-2">Fastest 3</h3>
              <ul className="space-y-1.5 text-sm">
                {fastest3.map((it) => (
                  <li key={it.item_id} className="flex items-baseline gap-2">
                    <span className="font-mono text-[11px] text-navy w-12 flex-shrink-0">{it.item_id}</span>
                    <span className="flex-1 text-ink/80 leading-snug">{it.text}</span>
                    <span className="text-muted text-xs tabular-nums whitespace-nowrap">{fmtSec(it.response_time_ms)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="eyebrow text-navy mb-2">Most deliberated</h3>
              <ul className="space-y-1.5 text-sm">
                {slowest3.map((it) => (
                  <li key={it.item_id} className="flex items-baseline gap-2">
                    <span className="font-mono text-[11px] text-navy w-12 flex-shrink-0">{it.item_id}</span>
                    <span className="flex-1 text-ink/80 leading-snug">{it.text}</span>
                    <span className="text-muted text-xs tabular-nums whitespace-nowrap">{fmtSec(it.response_time_ms)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white border border-hairline p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="eyebrow text-navy">All 20 responses</h2>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="form-input py-1.5 text-xs max-w-[220px]" aria-label="Sort responses">
            <option value="order">Sort: display position</option>
            <option value="rt_desc">Sort: response time (slow → fast)</option>
            <option value="rt_asc">Sort: response time (fast → slow)</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider2 text-muted border-b border-hairline">
                <th scope="col" className="text-left px-3 py-2 w-8">#</th>
                <th scope="col" className="text-left px-3 py-2">Item</th>
                <th scope="col" className="text-left px-3 py-2">Scale</th>
                <th scope="col" className="text-left px-3 py-2">Subscale</th>
                <th scope="col" className="text-left px-3 py-2">Value</th>
                <th scope="col" className="text-left px-3 py-2">Response time</th>
                <th scope="col" className="text-left px-3 py-2">Band</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.length === 0 && <tr><td colSpan={7} className="px-3 py-5 text-muted italic text-sm">No responses on file.</td></tr>}
              {sortedItems.map((it, i) => {
                const c = RT_BAND_COLOURS[it.response_time_band] || RT_BAND_COLOURS.normal;
                return (
                  <tr key={it.item_id || i} className="border-b border-hairline">
                    <td className="px-3 py-2 text-ink/70 tabular-nums">{i + 1}</td>
                    <td className="px-3 py-2">
                      <div className="font-mono text-[11px] text-navy">{it.item_id}{it.is_reverse_keyed ? <span className="text-gold-dark">R</span> : ''}</div>
                      <div className="text-xs text-ink/70 leading-snug max-w-[420px]">{it.text}</div>
                    </td>
                    <td className="px-3 py-2 text-ink/80">{it.scale || '—'}</td>
                    <td className="px-3 py-2 text-ink/80 capitalize">{it.subscale ? it.subscale.replace(/_/g, ' ') : '—'}</td>
                    <td className="px-3 py-2 text-navy font-medium tabular-nums">{it.value ?? '—'}</td>
                    <td className="px-3 py-2 text-ink/80 tabular-nums">{fmtSec(it.response_time_ms)}</td>
                    <td className="px-3 py-2">
                      <span className="inline-block text-[10px] uppercase tracking-wider2 px-2 py-0.5"
                            style={{ background: c.bg, color: c.fg }}>
                        {c.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// 20-cell heatmap — each cell is a square with the item id and tooltip.
// LA block + thin gold divider + TA block reflect the actual scale grouping;
// items inside each scale render in DISPLAY order (i.e. the participant's
// randomised order), per the brief.
function ResponseTimeHeatmap({ items }) {
  const laItems = items.filter((it) => it.scale === 'LA');
  const taItems = items.filter((it) => it.scale === 'TA');

  const cell = (it) => {
    const c = RT_BAND_COLOURS[it.response_time_band] || RT_BAND_COLOURS.normal;
    const titleText = `${it.item_id}${it.is_reverse_keyed ? ' (reverse-keyed)' : ''} — ${it.text}\nValue: ${it.value} · Response: ${fmtSec(it.response_time_ms)} · ${c.label}`;
    return (
      <button
        key={it.item_id}
        type="button"
        title={titleText}
        aria-label={`${it.item_id}: ${c.label}, ${fmtSec(it.response_time_ms)}`}
        className="w-12 h-12 text-[10px] font-mono flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-1"
        style={{ background: c.bg, color: c.fg }}
      >
        {it.item_id.replace(/^([LT]A)/, '$1\u00a0').replace(/\s/g, '')}
      </button>
    );
  };

  return (
    <div className="mt-4">
      <div className="flex items-center gap-1 flex-wrap">
        {laItems.map(cell)}
        {laItems.length > 0 && taItems.length > 0 && (
          <span aria-hidden="true" className="inline-block w-px h-12 bg-gold mx-2" />
        )}
        {taItems.map(cell)}
      </div>
      <div className="mt-1 flex items-center gap-1 text-[10px] uppercase tracking-wider2 text-muted">
        <span style={{ width: laItems.length * 52 }}>Learning Agility</span>
        <span aria-hidden="true" className="inline-block w-2" />
        <span style={{ width: taItems.length * 52 }}>Tolerance for Ambiguity</span>
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
function AIDiscussionTab({ doc, engagement }) {
  const [showJson, setShowJson] = useState(false);
  const convo = doc.conversation || [];
  const af = doc.scores?.ai_fluency || {};

  // Build a lookup from conversation array index → engagement turn (if avail).
  // Engagement skips kind=='dev' turns, so we re-map by stripping dev turns
  // here too.
  const publicConvo = convo.filter((t) => t.kind !== 'dev');
  const engTurns = engagement?.turns || [];

  const us = engagement?.user_summary;
  const as = engagement?.assistant_summary;

  return (
    <div id="panel-ai" className="space-y-6">
      {/* ---- Phase 11B: stat strip + sparklines ---- */}
      {(us || as) && (
        <div className="bg-white border border-hairline border-t-[3px] border-t-gold p-5">
          <h2 className="eyebrow text-navy mb-3">Conversation engagement</h2>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
            {us && <>
              <span><strong className="text-navy">{us.total_turns}</strong> user turns</span>
              <span className="text-muted">avg <strong className="text-ink/80">{us.avg_words_per_turn}</strong> words</span>
              <span className="text-muted">avg time to respond <strong className="text-ink/80">{fmtSec(us.avg_time_to_respond_ms)}</strong></span>
            </>}
            {as && <>
              <span className="text-muted mx-2 hidden md:inline">·</span>
              <span><strong className="text-navy">{as.total_turns}</strong> assistant turns</span>
              <span className="text-muted">avg latency <strong className="text-ink/80">{fmtSec(as.avg_latency_ms)}</strong></span>
              <span className={as.fallbacks_total > 0 ? 'text-terracotta' : 'text-muted'}>
                <strong>{as.fallbacks_total}</strong> fallback{as.fallbacks_total === 1 ? '' : 's'}
              </span>
            </>}
          </div>

          {us && engTurns.length > 0 && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
              <Sparkline
                title="Words per user turn"
                stroke="#1e3a5f"
                values={engTurns.filter((t) => t.role === 'user').map((t) => t.content_length_words)}
                yLabel={(v) => `${v}w`}
              />
              <Sparkline
                title="Time to respond per user turn"
                stroke="#b88a2a"
                values={engTurns.filter((t) => t.role === 'user').map((t) => Math.round((t.time_to_respond_ms || 0) / 1000))}
                yLabel={(v) => `${v}s`}
              />
            </div>
          )}
        </div>
      )}

      <div className="bg-white border border-hairline p-5">
        <h2 className="eyebrow text-navy">Conversation ({publicConvo.filter(t => t.role === 'user').length} user turns)</h2>
        <div className="mt-4 space-y-4">
          {publicConvo.length === 0 && <p className="text-sm text-muted italic">No conversation on record.</p>}
          {publicConvo.map((t, i) => {
            const eng = engTurns[i] || null;
            const isLongest = us && eng && eng.role === 'user' && eng.turn_index === us.longest_turn_index;
            const isSlowest = us && eng && eng.role === 'user' && eng.turn_index === us.slowest_response_turn_index;
            return (
              <div key={i} className={'p-4 border ' + (t.role === 'assistant' ? 'border-hairline bg-mist' : 'border-navy/10 bg-white')}>
                <div className="flex items-center justify-between mb-2 text-[11px] uppercase tracking-wider2">
                  <span className={t.role === 'assistant' ? 'text-gold-dark font-medium' : 'text-navy font-medium'}>
                    {t.role === 'assistant' ? 'Interviewer' : t.role === 'user' ? 'Participant' : t.role}
                  </span>
                  <span className="text-muted">{t.timestamp ? fmtDate(t.timestamp) : ''}</span>
                </div>
                <p className="text-[14px] text-ink/85 leading-relaxed whitespace-pre-wrap">{t.content}</p>

                {/* Phase 11B — per-turn metadata strip + pills */}
                {eng && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] uppercase tracking-wider2 text-muted">
                    {eng.role === 'user' ? (
                      <>
                        <span className="text-ink/60"><strong className="text-ink/80">{eng.content_length_words}</strong> words</span>
                        {eng.time_to_respond_ms !== null && eng.time_to_respond_ms !== undefined && (
                          <span className="text-ink/60"><strong className="text-ink/80">{fmtSec(eng.time_to_respond_ms)}</strong> to respond</span>
                        )}
                        {isLongest && (
                          <span className="bg-navy text-white px-2 py-0.5 normal-case tracking-normal text-[10px]">Longest turn</span>
                        )}
                        {isSlowest && (
                          <span className="bg-gold text-navy px-2 py-0.5 normal-case tracking-normal text-[10px]">Slowest response</span>
                        )}
                      </>
                    ) : (
                      <>
                        {eng.model && <span className="font-mono normal-case tracking-normal">model {eng.model}</span>}
                        {eng.model_latency_ms !== null && eng.model_latency_ms !== undefined && (
                          <span className="text-ink/60"><strong className="text-ink/80">{fmtSec(eng.model_latency_ms)}</strong> latency</span>
                        )}
                        <span className={eng.fallbacks_tried > 0 ? 'text-terracotta' : 'text-ink/60'}>
                          fallbacks: <strong>{eng.fallbacks_tried}</strong>
                        </span>
                        <span className="text-ink/60"><strong className="text-ink/80">{eng.content_length_words}</strong> words</span>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
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

// Hand-rolled SVG sparkline. Values is an array of numbers (one per data
// point); X axis is implicit by index. yLabel renders end-of-line annotation.
function Sparkline({ title, stroke, values, yLabel }) {
  const w = 320, h = 56, pad = 6;
  const safe = (values || []).map((v) => Number(v) || 0);
  const max = Math.max(1, ...safe);
  const min = 0;
  const points = safe.map((v, i) => {
    const x = pad + (safe.length === 1 ? (w - 2 * pad) / 2 : (i / (safe.length - 1)) * (w - 2 * pad));
    const y = h - pad - ((v - min) / Math.max(1, (max - min))) * (h - 2 * pad);
    return [x, y];
  });
  const dPath = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const lastVal = safe[safe.length - 1];
  const maxVal = max;
  return (
    <div>
      <h3 className="eyebrow text-navy mb-2">{title}</h3>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={title} style={{ maxWidth: 360 }}>
        <title>{title}</title>
        <desc>{`Time-series across ${safe.length} user turns. Max ${yLabel(maxVal)}, latest ${yLabel(lastVal || 0)}.`}</desc>
        {/* Baseline */}
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#e5e7eb" strokeWidth={1} />
        {/* Path */}
        <path d={dPath} fill="none" stroke={stroke} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
        {/* Dots */}
        {points.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={2.2} fill={stroke}>
            <title>{`Turn ${i + 1}: ${yLabel(safe[i])}`}</title>
          </circle>
        ))}
      </svg>
      <p className="text-[10px] uppercase tracking-wider2 text-muted">
        max {yLabel(maxVal)} · latest {yLabel(lastVal || 0)}
      </p>
    </div>
  );
}

// -------- Scenario Tab -------- //
const SCN_PHASE_LABEL = {
  read: 'Read',
  part1: 'Part 1',
  curveball: 'Curveball',
  part2: 'Part 2',
};

function fmtDurationMin(ms) {
  if (ms === null || ms === undefined || ms === 0) return '0s';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const r = sec % 60;
  return r ? `${m}m ${r}s` : `${m}m`;
}

function ScenarioTab({ doc, engagement }) {
  const scn = doc.scenario || {};
  const scores = doc.scores?.scenario || {};
  const p1 = scn.part1_response || {};
  const p2 = scn.part2_response || {};
  const phases = engagement?.phases || [];
  const summary = engagement?.summary || null;

  return (
    <div id="panel-scenario" className="space-y-6">
      {/* ---- Phase 11B: stacked-bar engagement visualisation + stat strip ---- */}
      {summary && phases.length > 0 && (
        <div className="bg-white border border-hairline border-t-[3px] border-t-gold p-5">
          <h2 className="eyebrow text-navy mb-3">Time on each phase</h2>
          <ScenarioPhaseBars phases={phases} />
          <div className="mt-4 flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
            <span><strong className="text-navy">Total time:</strong> {fmtDurationMin(summary.total_actual_ms)}</span>
            <span className="text-muted">target {fmtDurationMin(summary.total_target_ms)}</span>
            {summary.most_engaged_phase && (
              <span>
                <strong className="text-navy">Most engaged:</strong>{' '}
                {SCN_PHASE_LABEL[summary.most_engaged_phase] || summary.most_engaged_phase}{' '}
                <span className="text-muted">
                  ({fmtDurationMin(phases.find((p) => p.phase === summary.most_engaged_phase)?.actual_ms || 0)},{' '}
                  {(phases.find((p) => p.phase === summary.most_engaged_phase)?.ratio || 0).toFixed(2)}× target)
                </span>
              </span>
            )}
            {summary.least_engaged_phase && summary.least_engaged_phase !== summary.most_engaged_phase && (
              <span>
                <strong className="text-navy">Least engaged:</strong>{' '}
                {SCN_PHASE_LABEL[summary.least_engaged_phase] || summary.least_engaged_phase}{' '}
                <span className="text-muted">
                  ({fmtDurationMin(phases.find((p) => p.phase === summary.least_engaged_phase)?.actual_ms || 0)},{' '}
                  {(phases.find((p) => p.phase === summary.least_engaged_phase)?.ratio || 0).toFixed(2)}× target)
                </span>
              </span>
            )}
          </div>
        </div>
      )}

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

// Hand-rolled SVG: 4 horizontal stacked bars, one per phase. Each bar shows
// actual time (navy fill) inside the target band (light grey track). When
// actual exceeds target, the overrun extends past a vertical target line and
// the overrun tip renders in terracotta.
function ScenarioPhaseBars({ phases }) {
  // Compute a shared X scale: max of (any actual_ms, any target_ms × 1.05).
  const maxTarget = Math.max(...phases.map((p) => p.target_ms));
  const maxActual = Math.max(...phases.map((p) => p.actual_ms));
  // Cap visual bar at 2× the longest target to keep one outlier from
  // shrinking everything else. The label always shows the true value.
  const cap = Math.max(maxTarget * 2, maxActual);
  const xMax = Math.min(cap, Math.max(maxTarget * 1.1, maxActual));

  const W = 720, BAR_H = 24, ROW_H = 40, LABEL_W = 110, RIGHT_W = 130;
  const TRACK_X = LABEL_W;
  const TRACK_W = W - LABEL_W - RIGHT_W;
  const xFor = (ms) => (xMax > 0 ? (ms / xMax) * TRACK_W : 0);
  const H = phases.length * ROW_H + 18;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-labelledby="phase-bars-title phase-bars-desc"
         style={{ maxWidth: 760 }}>
      <title id="phase-bars-title">Scenario phase time vs target</title>
      <desc id="phase-bars-desc">{`Four horizontal bars showing actual time spent in each scenario phase against its target. ${phases.filter((p) => p.overran).length} phases overran their target.`}</desc>

      {phases.map((p, i) => {
        const y = i * ROW_H + 10;
        const targetW = xFor(p.target_ms);
        const actualW = xFor(Math.min(p.actual_ms, xMax));
        const overran = p.overran;
        const cappedNote = p.actual_ms > xMax;
        return (
          <g key={p.phase}>
            {/* Phase label */}
            <text x={LABEL_W - 8} y={y + BAR_H / 2 + 4} fontSize="11" fill="#1e3a5f" textAnchor="end" fontWeight="500">
              {SCN_PHASE_LABEL[p.phase] || p.phase}
            </text>
            {/* Target track */}
            <rect x={TRACK_X} y={y} width={targetW} height={BAR_H} fill="#f3f4f6" stroke="#e5e7eb" strokeWidth={1} />
            {/* Actual fill (navy) */}
            <rect x={TRACK_X} y={y + 4} width={Math.min(actualW, targetW)} height={BAR_H - 8} fill="#1e3a5f" />
            {/* Overrun (terracotta) past the target line */}
            {overran && (
              <rect x={TRACK_X + targetW} y={y + 4} width={Math.max(0, actualW - targetW)} height={BAR_H - 8} fill="#b94c3a" />
            )}
            {/* Target end-line */}
            <line x1={TRACK_X + targetW} y1={y - 2} x2={TRACK_X + targetW} y2={y + BAR_H + 2} stroke="#1e3a5f" strokeWidth={1} strokeDasharray="2 2" />
            {/* Right-side label: actual / target / ratio */}
            <text x={TRACK_X + TRACK_W + 8} y={y + BAR_H / 2 + 4} fontSize="11" fill="#374151">
              <tspan fontWeight="600" fill="#1e3a5f">{fmtDurationMin(p.actual_ms)}</tspan>
              <tspan fill="#9ca3af"> / {fmtDurationMin(p.target_ms)}</tspan>
              <tspan fill={overran ? '#b94c3a' : '#9ca3af'}> · {p.ratio.toFixed(2)}×</tspan>
              {cappedNote && <tspan fill="#b94c3a"> ↗</tspan>}
            </text>
          </g>
        );
      })}
    </svg>
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
