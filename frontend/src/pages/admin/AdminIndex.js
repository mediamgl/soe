import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, AlertTriangle } from 'lucide-react';
import { getDashboardSummary, listSessions, apiErrorMessage } from '../../lib/adminApi';
import StatTile from '../../components/admin/StatTile';
import Donut from '../../components/admin/Donut';
import DimensionBars from '../../components/admin/DimensionBars';
import ActivityChart from '../../components/admin/ActivityChart';
import ScoreChip from '../../components/admin/ScoreChip';

function fmtDuration(sec) {
  if (!sec && sec !== 0) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m` : `${h}h`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }); }
  catch { return iso.slice(0, 10); }
}

export default function AdminIndex() {
  const [summary, setSummary] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloading, setReloading] = useState(false);

  async function load() {
    try {
      setError(null);
      const [s, l] = await Promise.all([
        getDashboardSummary(),
        listSessions({ page: 1, page_size: 10, sort: '-created_at' }),
      ]);
      setSummary(s);
      setRecent(l.items || []);
    } catch (e) {
      setError(apiErrorMessage(e, 'Could not load dashboard.'));
    } finally {
      setLoading(false);
      setReloading(false);
    }
  }

  useEffect(() => { load(); /* initial */ }, []);

  const deltaWeek = useMemo(() => {
    if (!summary) return null;
    const t = summary.completed_this_week, l = summary.completed_last_week;
    if (!t && !l) return { dir: null, label: null };
    if (l === 0) return { dir: 'up', label: `+${t} vs last week` };
    const d = t - l;
    return {
      dir: d >= 0 ? 'up' : 'down',
      label: `${d >= 0 ? '+' : ''}${d} vs last week`,
    };
  }, [summary]);

  return (
    <section>
      <div className="flex items-start justify-between mb-8">
        <div>
          <span className="eyebrow">Admin</span>
          <h1 className="mt-1 font-serif text-3xl md:text-4xl text-navy tracking-tight">Overview</h1>
          <p className="mt-2 text-sm text-muted">{summary?.totals?.total_sessions ?? '—'} sessions tracked across the preview environment.</p>
        </div>
        <button
          type="button"
          onClick={() => { setReloading(true); load(); }}
          className="btn-ghost"
          aria-label="Refresh dashboard"
        >
          <RefreshCw className={`w-4 h-4 ${reloading ? 'animate-spin' : ''}`} strokeWidth={2} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="card-gold-top mb-6 flex items-start gap-3 text-sm">
          <AlertTriangle className="w-4 h-4 text-terracotta mt-0.5" strokeWidth={2} />
          <div><strong className="text-navy">Could not load dashboard.</strong><p className="text-muted">{error}</p></div>
        </div>
      )}

      {/* Stat tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile
          label="Total sessions"
          value={loading ? null : summary?.totals?.total_sessions}
          loading={loading}
          sparkValues={summary ? summary.activity_14d.map((d) => d.new_sessions) : []}
          accent="navy"
        />
        <StatTile
          label="Completed this week"
          value={loading ? null : summary?.completed_this_week}
          loading={loading}
          delta={deltaWeek?.label}
          deltaDir={deltaWeek?.dir}
          accent="navy"
        />
        <StatTile
          label="Avg completion time"
          value={loading ? null : (summary?.avg_completion_duration_seconds != null ? Math.round(summary.avg_completion_duration_seconds / 60) : '—')}
          unit="min"
          hint="Last 30 days"
          loading={loading}
          accent="navy"
        />
        <StatTile
          label="Expiring within 7 days"
          value={loading ? null : summary?.totals?.expiring_soon}
          accent="gold"
          loading={loading}
          hint={summary?.totals?.expiring_soon > 0 ? 'Review and archive if needed' : 'None — nothing to do'}
        />
      </div>

      {/* Score distribution + dimension averages */}
      <div className="mt-10 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-white border border-hairline p-6">
          <h2 className="eyebrow text-navy">Score distribution</h2>
          <p className="text-sm text-muted mt-1">Band breakdown across completed sessions, last 30 days.</p>
          <div className="mt-5">
            {loading ? <div className="h-[180px] bg-hairline/40 animate-pulse" /> : (
              <Donut data={summary?.score_distribution || {}} />
            )}
          </div>
        </div>
        <div className="bg-white border border-hairline p-6">
          <h2 className="eyebrow text-navy">Dimension averages</h2>
          <p className="text-sm text-muted mt-1">Mean score per assessed dimension, coloured by band.</p>
          <div className="mt-5">
            {loading ? <div className="h-[180px] bg-hairline/40 animate-pulse" /> : (
              <DimensionBars rows={summary?.dimension_averages || []} />
            )}
          </div>
        </div>
      </div>

      {/* Recent sessions + activity */}
      <div className="mt-10 grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="bg-white border border-hairline p-6 lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <h2 className="eyebrow text-navy">Recent sessions</h2>
            <Link to="/admin/sessions" className="text-xs uppercase tracking-wider2 text-navy hover:text-gold border-b border-transparent hover:border-gold pb-0.5">
              View all
            </Link>
          </div>
          <div className="mt-4 -mx-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider2 text-muted border-b border-hairline">
                  <th className="text-left px-6 py-2 font-medium">Participant</th>
                  <th className="text-left px-6 py-2 font-medium">Stage</th>
                  <th className="text-left px-6 py-2 font-medium">Category</th>
                  <th className="text-left px-6 py-2 font-medium">Created</th>
                  <th className="text-left px-6 py-2 font-medium">Duration</th>
                </tr>
              </thead>
              <tbody>
                {loading && Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-hairline">
                    {Array.from({ length: 5 }).map((_, j) => (
                      <td key={j} className="px-6 py-3"><div className="h-3 bg-hairline animate-pulse w-24" /></td>
                    ))}
                  </tr>
                ))}
                {!loading && recent.length === 0 && (
                  <tr><td colSpan={5} className="px-6 py-6 text-muted italic text-sm">No sessions yet.</td></tr>
                )}
                {!loading && recent.map((r) => (
                  <tr key={r.session_id} className="border-b border-hairline hover:bg-mist transition-colors cursor-pointer">
                    <td className="px-6 py-3">
                      <Link to={`/admin/sessions/${r.session_id}`} className="text-navy font-medium hover:text-gold">
                        {r.redacted ? <span className="italic text-muted">(redacted)</span> : (r.participant?.name || '—')}
                      </Link>
                      {r.participant?.organisation && !r.redacted && <div className="text-[11px] text-muted">{r.participant.organisation}</div>}
                    </td>
                    <td className="px-6 py-3 text-ink/80">{r.stage || '—'}</td>
                    <td className="px-6 py-3"><ScoreChip colour={r.overall_colour} size="sm">{r.overall_category || 'n/a'}</ScoreChip></td>
                    <td className="px-6 py-3 text-ink/80">{fmtDate(r.created_at)}</td>
                    <td className="px-6 py-3 text-ink/80">{fmtDuration(r.duration_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="bg-white border border-hairline p-6">
          <h2 className="eyebrow text-navy">Activity · 14 days</h2>
          <div className="mt-5">
            {loading ? <div className="h-[140px] bg-hairline/40 animate-pulse" /> : (
              <ActivityChart data={summary?.activity_14d || []} />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
