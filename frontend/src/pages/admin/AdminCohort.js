import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, Printer, ExternalLink } from 'lucide-react';
import { cohortSessions, apiErrorMessage } from '../../lib/adminApi';

// Phase 11C — cohort view. Reads /api/admin/sessions/cohort, renders 9 sections.
// All charts hand-rolled SVG; palette navy / gold / terracotta; print-friendly.

// ------------------------------------------------------------------- helpers
function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return iso.slice(0, 10); }
}
function fmtScore(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return n.toFixed(1);
}
function fmtDuration(sec) {
  if (!sec && sec !== 0) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
}

// Five-bucket band scheme matching cohort_service. Cell colour palette per
// the brief: Exceptional=deep navy, Strong=navy, Moderate=gold,
// Limited=terracotta light, Low=terracotta deep.
const BAND_FOR = (s) => {
  if (s === null || s === undefined) return null;
  const n = Number(s);
  if (n >= 4.5) return 'Exceptional';
  if (n >= 4.0) return 'Strong';
  if (n >= 3.0) return 'Moderate';
  if (n >= 2.0) return 'Limited';
  return 'Low';
};
const BAND_COLOURS = {
  Exceptional: { bg: '#0f1f33', fg: '#ffffff' },  // deep navy
  Strong:      { bg: '#1e3a5f', fg: '#ffffff' },  // navy
  Moderate:    { bg: '#d4a84b', fg: '#1e3a5f' },  // gold
  Limited:     { bg: '#e8a08e', fg: '#1e3a5f' },  // light terracotta
  Low:         { bg: '#b94c3a', fg: '#ffffff' },  // deep terracotta
};
const BAND_ORDER = ['Exceptional', 'Strong', 'Moderate', 'Limited', 'Low'];

// ------------------------------------------------------------- main page
export default function AdminCohort() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const idsParam = searchParams.get('ids') || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const ids = useMemo(
    () => idsParam.split(',').map((s) => s.trim()).filter(Boolean),
    [idsParam],
  );

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true); setError(null); setData(null);
      if (ids.length < 2) {
        setError('Cohort view requires at least 2 sessions.');
        setLoading(false);
        return;
      }
      if (ids.length > 50) {
        setError('Cohort view supports up to 50 sessions.');
        setLoading(false);
        return;
      }
      try {
        const d = await cohortSessions(ids);
        if (alive) setData(d);
      } catch (e) {
        if (!alive) return;
        const detail = e?.response?.data?.detail;
        if (detail && typeof detail === 'object' && Array.isArray(detail.incomplete)) {
          const reasons = detail.incomplete
            .map((x) => `${(x.session_id || '').slice(0, 8)}… (${x.reasons.join(', ')})`)
            .join(' · ');
          setError(`${detail.message} ${reasons}`);
        } else if (detail && typeof detail === 'object' && Array.isArray(detail.missing)) {
          setError(`${detail.message} Missing: ${detail.missing.join(', ')}`);
        } else {
          setError(apiErrorMessage(e, 'Could not load cohort.'));
        }
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => { alive = false; };
  }, [idsParam]);    // eslint-disable-line

  if (loading) {
    return <section><p className="text-muted italic">Loading cohort…</p></section>;
  }
  if (error) {
    return (
      <section>
        <div className="bg-white border border-terracotta/40 p-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-terracotta mt-0.5 flex-shrink-0" />
            <div>
              <h1 className="font-serif text-xl text-navy">Cohort unavailable</h1>
              <p className="mt-2 text-sm text-ink/80">{error}</p>
              <Link to="/admin/sessions" className="mt-4 inline-flex items-center gap-2 text-sm text-navy hover:text-gold border-b border-transparent hover:border-gold">
                <ArrowLeft className="w-4 h-4" /> Back to sessions
              </Link>
            </div>
          </div>
        </div>
      </section>
    );
  }
  if (!data) return null;

  const N = data.cohort_summary?.n || 0;
  const refineLink = `/admin/sessions?` + ids.map((id, i) => `bulk[${i}]=${encodeURIComponent(id)}`).join('&');

  return (
    <section className="cohort-print">
      <style>{`
        @media print {
          @page { size: A4 landscape; margin: 12mm; }
          .cohort-no-print { display: none !important; }
          .cohort-section { page-break-inside: avoid; break-inside: avoid; }
          .cohort-heatmap { page-break-inside: avoid; }
        }
      `}</style>

      {/* 1. Header strip */}
      <div className="cohort-section flex items-start justify-between mb-6 flex-wrap gap-3">
        <div>
          <span className="eyebrow">Admin · Cohort</span>
          <h1 className="mt-1 font-serif text-3xl md:text-4xl text-navy tracking-tight">
            Cohort View — {N} participant{N === 1 ? '' : 's'}
          </h1>
          <p className="mt-2 text-sm text-muted">
            {(data.participants || []).map((p) => p.label).join(' · ')}
          </p>
        </div>
        <div className="cohort-no-print flex items-center gap-3">
          <button
            type="button"
            onClick={() => window.print()}
            className="btn-ghost py-2 px-3 text-xs uppercase tracking-wider2 inline-flex items-center gap-2"
          >
            <Printer className="w-4 h-4" /> Print
          </button>
          <Link to="/admin/sessions" className="text-xs uppercase tracking-wider2 text-navy hover:text-gold inline-flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" /> Back to sessions
          </Link>
        </div>
      </div>

      {/* 2. Cohort summary card */}
      <CohortSummaryCard summary={data.cohort_summary} />

      {/* 3. Dimension distribution panel */}
      <DimensionDistribution stats={data.dimension_stats || []} />

      {/* 4. Heatmap */}
      <CohortHeatmap heatmap={data.heatmap} dimLabels={dimLabelMap(data.dimension_stats)} />

      {/* 5. Cohort type panel */}
      <CohortTypePanel cohortType={data.cohort_type} />

      {/* 6. Outlier panel */}
      <OutlierPanel outliers={data.outliers || []} />

      {/* 7. Category distribution donut + 8. flag summary */}
      <div className="cohort-section grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
        <div className="bg-white border border-hairline p-5 md:col-span-1">
          <h2 className="font-serif text-lg text-navy mb-3">Overall category distribution</h2>
          <CategoryDonut counts={data.category_distribution || {}} total={N} />
        </div>
        <div className="bg-white border border-hairline p-5 md:col-span-2">
          <h2 className="font-serif text-lg text-navy mb-3">Response-pattern flags</h2>
          <FlagSummary flags={data.flag_summary || {}} />
        </div>
      </div>

      {/* 9. Footer */}
      <div className="cohort-section flex items-center justify-between text-xs text-muted pt-4 border-t border-hairline">
        <span>Cohort generated {fmtDate(data.generated_at)}.</span>
        <button
          type="button"
          onClick={() => navigate('/admin/sessions')}
          className="cohort-no-print text-navy hover:text-gold inline-flex items-center gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to sessions
        </button>
      </div>
    </section>
  );
}

function dimLabelMap(stats) {
  const m = {};
  (stats || []).forEach((s) => { m[s.dimension_id] = s.label; });
  return m;
}

// ------------------------------------------------------------- 2. summary
function CohortSummaryCard({ summary }) {
  if (!summary) return null;
  const range = summary.completion_date_range || {};
  return (
    <div className="cohort-section bg-white border border-hairline border-t-[3px] border-t-navy p-5 mb-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <div className="eyebrow">Participants</div>
          <div className="mt-1 text-2xl font-serif text-navy">{summary.n}</div>
        </div>
        <div>
          <div className="eyebrow">Completion range</div>
          <div className="mt-1 text-ink/80">{fmtDate(range.earliest)} → {fmtDate(range.latest)}</div>
        </div>
        <div>
          <div className="eyebrow">Avg session</div>
          <div className="mt-1 text-ink/80">{fmtDuration(summary.avg_session_duration_seconds)}</div>
        </div>
        <div>
          <div className="eyebrow">Organisations ({(summary.organisations || []).length})</div>
          <div className="mt-1 text-ink/80 text-xs leading-snug">
            {(summary.organisations || []).join(', ') || '—'}
          </div>
        </div>
      </div>
    </div>
  );
}

// -------------------------------- 3. dimension distribution (violin-lite)
function DimensionDistribution({ stats }) {
  if (!stats.length) return null;
  // SVG geometry — one row per dimension, 32px tall each
  const ROW_H = 32;
  const W = 760, LABEL_W = 200, RIGHT_W = 80;
  const TRACK_X = LABEL_W;
  const TRACK_W = W - LABEL_W - RIGHT_W;
  const xFor = (score) => TRACK_X + ((score - 1) / 4) * TRACK_W;   // 1.0 → left, 5.0 → right
  const H = stats.length * ROW_H + 32;

  return (
    <div className="cohort-section bg-white border border-hairline p-5 mb-6 overflow-x-auto">
      <h2 className="font-serif text-lg text-navy mb-1">Dimension distribution</h2>
      <p className="text-xs text-muted mb-3">
        Per-dimension range, IQR (mid-navy box), median (gold tick), and cohort mean (navy circle).
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth: 640 }} role="img"
           aria-labelledby="dim-dist-title dim-dist-desc">
        <title id="dim-dist-title">Cohort dimension distribution</title>
        <desc id="dim-dist-desc">Six horizontal range bars, one per leadership-readiness dimension, showing min-to-max span, interquartile box, median, and mean for the cohort.</desc>

        {/* Score scale ticks (top) */}
        {[1, 2, 3, 4, 5].map((v) => (
          <g key={v}>
            <line x1={xFor(v)} y1={4} x2={xFor(v)} y2={H - 12} stroke="#e5e7eb" strokeWidth={1} />
            <text x={xFor(v)} y={H - 2} fontSize="9" fill="#9ca3af" textAnchor="middle">{v}</text>
          </g>
        ))}

        {stats.map((r, i) => {
          const y = i * ROW_H + 14;
          const x_min = xFor(r.min);
          const x_max = xFor(r.max);
          const x_p25 = xFor(r.p25);
          const x_p75 = xFor(r.p75);
          const x_med = xFor(r.median);
          const x_mean = xFor(r.mean);
          return (
            <g key={r.dimension_id}>
              {/* Dimension label */}
              <text x={LABEL_W - 8} y={y + 4} fontSize="11" fill="#1e3a5f" textAnchor="end" fontWeight="500">
                {r.label}
              </text>
              {/* Range whisker (min..max) */}
              {r.n > 0 && (
                <line x1={x_min} y1={y} x2={x_max} y2={y} stroke="#1e3a5f" strokeOpacity={0.35} strokeWidth={1.5} />
              )}
              {/* IQR box */}
              {r.n > 0 && x_p75 > x_p25 && (
                <rect x={x_p25} y={y - 6} width={x_p75 - x_p25} height={12} fill="#1e3a5f" fillOpacity={0.30} stroke="#1e3a5f" strokeWidth={1} />
              )}
              {/* Median tick (gold) */}
              {r.n > 0 && (
                <line x1={x_med} y1={y - 7} x2={x_med} y2={y + 7} stroke="#b88a2a" strokeWidth={2.5} />
              )}
              {/* Mean dot (navy) */}
              {r.n > 0 && (
                <circle cx={x_mean} cy={y} r={3.5} fill="#1e3a5f" stroke="#ffffff" strokeWidth={1.2}>
                  <title>{`${r.label} — mean ${r.mean.toFixed(2)}, median ${r.median.toFixed(2)}`}</title>
                </circle>
              )}
              {/* Right-side mean text */}
              <text x={W - RIGHT_W + 6} y={y + 4} fontSize="11" fill="#374151">
                <tspan fontWeight="600" fill="#1e3a5f">{r.mean.toFixed(2)}</tspan>
                <tspan fill="#9ca3af">  σ {r.std_dev.toFixed(2)}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] uppercase tracking-wider2 text-muted">
        <span><span className="inline-block w-3 h-3 mr-1.5 align-middle" style={{ background: '#1e3a5f', opacity: 0.30 }} aria-hidden="true" />IQR</span>
        <span><span className="inline-block w-1 h-3 mr-1.5 align-middle" style={{ background: '#b88a2a' }} aria-hidden="true" />Median</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-full mr-1.5 align-middle" style={{ background: '#1e3a5f' }} aria-hidden="true" />Mean</span>
      </div>
    </div>
  );
}

// -------------------------------- 4. heatmap
function CohortHeatmap({ heatmap, dimLabels }) {
  if (!heatmap?.rows?.length) return null;
  const { axis_order, rows } = heatmap;
  return (
    <div className="cohort-section cohort-heatmap bg-white border border-hairline p-5 mb-6 overflow-x-auto">
      <h2 className="font-serif text-lg text-navy mb-1">Heatmap</h2>
      <p className="text-xs text-muted mb-3">
        Each cell shows a participant's score on that dimension, banded by colour. Click a row label to open the participant detail.
      </p>
      <table className="text-sm border-collapse">
        <thead>
          <tr>
            <th scope="col" className="text-left px-2 py-2 text-[10px] uppercase tracking-wider2 text-muted font-medium">Participant</th>
            {axis_order.map((id) => (
              <th key={id} scope="col"
                  className="px-2 py-2 text-[10px] uppercase tracking-wider2 text-muted font-medium align-bottom"
                  style={{ minWidth: 70 }}>
                <div style={{
                  writingMode: 'horizontal-tb',
                  whiteSpace: 'normal',
                  maxWidth: 80,
                  lineHeight: 1.1,
                }}>{dimLabels[id] || id.replace(/_/g, ' ')}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.session_id}>
              <th scope="row" className="text-left px-2 py-1 align-middle">
                <Link to={`/admin/sessions/${r.session_id}`}
                      target="_blank" rel="noreferrer"
                      className="text-navy hover:text-gold text-sm font-medium inline-flex items-center gap-1">
                  {r.label}
                  <ExternalLink className="w-3 h-3 opacity-50" aria-hidden="true" />
                </Link>
              </th>
              {axis_order.map((dimId, i) => {
                const score = r.scores[i];
                const band = BAND_FOR(score);
                const c = band ? BAND_COLOURS[band] : { bg: '#f3f4f6', fg: '#9ca3af' };
                return (
                  <td key={dimId} className="p-0">
                    <div
                      tabIndex={0}
                      role="img"
                      aria-label={
                        score === null
                          ? `${r.name || r.label} — ${dimLabels[dimId] || dimId}: no data`
                          : `${r.name || r.label} — ${dimLabels[dimId] || dimId}: ${fmtScore(score)}, ${band}`
                      }
                      title={
                        score === null
                          ? `${r.name || r.label} — ${dimLabels[dimId] || dimId}: no data`
                          : `${r.name || r.label} — ${dimLabels[dimId] || dimId}\nScore: ${fmtScore(score)} · ${band}`
                      }
                      className="m-1 px-2 py-3 text-center text-sm font-medium tabular-nums focus:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-1"
                      style={{ background: c.bg, color: c.fg, minWidth: 60 }}
                    >
                      {score === null ? '—' : fmtScore(score)}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {/* Band legend */}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-wider2">
        {BAND_ORDER.map((b) => (
          <span key={b} className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-3" style={{ background: BAND_COLOURS[b].bg }} aria-hidden="true" />
            <span className="text-muted">{b}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// -------------------------------- 5. cohort type
function CohortTypePanel({ cohortType }) {
  if (!cohortType) return null;
  const top = cohortType.top_strengths || [];
  const dev = cohortType.top_dev_areas || [];
  return (
    <div className="cohort-section grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">
      <div className="bg-white border border-hairline border-t-[3px] border-t-navy p-5">
        <h2 className="font-serif text-lg text-navy mb-2">Cohort strengths</h2>
        <ol className="space-y-1.5 text-sm mb-3">
          {top.map((s, i) => (
            <li key={s.dimension_id} className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase tracking-wider2 text-muted w-5">{i + 1}.</span>
              <span className="font-medium text-navy flex-1">{s.label}</span>
              <span className="text-navy tabular-nums">{Number(s.mean).toFixed(2)}</span>
            </li>
          ))}
        </ol>
        <p className="text-sm text-ink/80 italic leading-relaxed">{cohortType.strength_summary}</p>
      </div>
      <div className="bg-white border border-hairline border-t-[3px] border-t-gold p-5">
        <h2 className="font-serif text-lg text-navy mb-2">Development priorities</h2>
        <ol className="space-y-1.5 text-sm mb-3">
          {dev.map((s, i) => (
            <li key={s.dimension_id} className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase tracking-wider2 text-muted w-5">{i + 1}.</span>
              <span className="font-medium text-navy flex-1">{s.label}</span>
              <span className="text-gold-dark tabular-nums">{Number(s.mean).toFixed(2)}</span>
            </li>
          ))}
        </ol>
        <p className="text-sm text-ink/80 italic leading-relaxed">{cohortType.dev_summary}</p>
      </div>
    </div>
  );
}

// -------------------------------- 6. outlier panel
function OutlierPanel({ outliers }) {
  const anyOutliers = outliers.some((o) => o.low_outliers.length || o.high_outliers.length);
  return (
    <div className="cohort-section bg-white border border-hairline p-5 mb-6">
      <h2 className="font-serif text-lg text-navy mb-1">Outliers</h2>
      <p className="text-xs text-muted mb-3">
        Participants whose dimension score is more than 1.5 standard deviations from the cohort mean.
      </p>
      {!anyOutliers && (
        <p className="text-sm text-muted italic">No outliers in this cohort.</p>
      )}
      {anyOutliers && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          {outliers.map((o) => {
            if (!o.low_outliers.length && !o.high_outliers.length) return null;
            return (
              <div key={o.dimension_id} className="border-l-2 border-hairline pl-3">
                <h3 className="text-navy font-medium mb-1">{o.label}</h3>
                {o.high_outliers.length > 0 && (
                  <div className="text-xs text-ink/80">
                    <span className="text-[10px] uppercase tracking-wider2 text-navy">High</span>{' '}
                    {o.high_outliers.map((p, i) => (
                      <React.Fragment key={p.session_id}>
                        {i > 0 && ', '}
                        <Link
                          to={`/admin/sessions/${p.session_id}`}
                          target="_blank" rel="noreferrer"
                          aria-label={`View ${p.name || p.label}'s session detail`}
                          className="text-navy hover:text-gold inline-flex items-center gap-0.5 underline decoration-dotted">
                          {p.label} ({fmtScore(p.score)}, +{Number(p.std_devs_above).toFixed(1)}σ)
                        </Link>
                      </React.Fragment>
                    ))}
                  </div>
                )}
                {o.low_outliers.length > 0 && (
                  <div className="text-xs text-ink/80 mt-0.5">
                    <span className="text-[10px] uppercase tracking-wider2 text-terracotta">Low</span>{' '}
                    {o.low_outliers.map((p, i) => (
                      <React.Fragment key={p.session_id}>
                        {i > 0 && ', '}
                        <Link
                          to={`/admin/sessions/${p.session_id}`}
                          target="_blank" rel="noreferrer"
                          aria-label={`View ${p.name || p.label}'s session detail`}
                          className="text-navy hover:text-gold inline-flex items-center gap-0.5 underline decoration-dotted">
                          {p.label} ({fmtScore(p.score)}, −{Number(p.std_devs_below).toFixed(1)}σ)
                        </Link>
                      </React.Fragment>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// -------------------------------- 7. category donut
const CAT_PALETTE = {
  'Transformation Ready':  '#1e3a5f',  // navy
  'High Potential':        '#b88a2a',  // gold dark
  'Development Required':  '#e8a08e',  // light terracotta
  'Limited Readiness':     '#b94c3a',  // deep terracotta
};
function CategoryDonut({ counts, total }) {
  const items = Object.keys(CAT_PALETTE).map((cat) => ({
    label: cat,
    value: counts[cat] || 0,
    colour: CAT_PALETTE[cat],
  }));
  const sum = items.reduce((a, b) => a + b.value, 0);
  if (!sum) return <p className="text-sm text-muted italic">No category data.</p>;

  const size = 140, cx = size / 2, cy = size / 2;
  const r_outer = 60, r_inner = 38;
  let cumulative = 0;
  const arcs = items.filter((it) => it.value > 0).map((it) => {
    const startA = (cumulative / sum) * Math.PI * 2 - Math.PI / 2;
    cumulative += it.value;
    const endA = (cumulative / sum) * Math.PI * 2 - Math.PI / 2;
    const large = (endA - startA) > Math.PI ? 1 : 0;
    const x1o = cx + r_outer * Math.cos(startA);
    const y1o = cy + r_outer * Math.sin(startA);
    const x2o = cx + r_outer * Math.cos(endA);
    const y2o = cy + r_outer * Math.sin(endA);
    const x1i = cx + r_inner * Math.cos(endA);
    const y1i = cy + r_inner * Math.sin(endA);
    const x2i = cx + r_inner * Math.cos(startA);
    const y2i = cy + r_inner * Math.sin(startA);
    const path = [
      `M${x1o.toFixed(2)},${y1o.toFixed(2)}`,
      `A${r_outer},${r_outer} 0 ${large} 1 ${x2o.toFixed(2)},${y2o.toFixed(2)}`,
      `L${x1i.toFixed(2)},${y1i.toFixed(2)}`,
      `A${r_inner},${r_inner} 0 ${large} 0 ${x2i.toFixed(2)},${y2i.toFixed(2)}`,
      'Z',
    ].join(' ');
    return { ...it, path };
  });

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <svg width={size} height={size} role="img" aria-label="Category distribution donut chart">
        <title>Category distribution</title>
        <desc>{`${sum} participants distributed across ${arcs.length} overall-readiness categories.`}</desc>
        {arcs.map((a) => (
          <path key={a.label} d={a.path} fill={a.colour}>
            <title>{`${a.label}: ${a.value} (${Math.round((a.value / sum) * 100)}%)`}</title>
          </path>
        ))}
        <text x={cx} y={cy + 4} fontSize="22" fill="#1e3a5f" fontFamily="serif" textAnchor="middle">{sum}</text>
      </svg>
      <ul className="text-xs space-y-1">
        {items.map((it) => (
          <li key={it.label} className="flex items-center gap-2">
            <span className="inline-block w-3 h-3" style={{ background: it.colour }} aria-hidden="true" />
            <span className="text-ink/80 flex-1">{it.label}</span>
            <span className="text-navy tabular-nums">{it.value}</span>
            <span className="text-muted tabular-nums">({total ? Math.round((it.value / total) * 100) : 0}%)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// -------------------------------- 8. flag summary
function FlagSummary({ flags }) {
  const total = flags.total_flagged || 0;
  if (total === 0) {
    return <p className="text-sm text-muted italic">No response-pattern flags in this cohort.</p>;
  }
  const breakdown = [
    { key: 'high_acquiescence',    label: 'High acquiescence' },
    { key: 'low_variance',         label: 'Low variance' },
    { key: 'extreme_response_bias', label: 'Extreme bias' },
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <span className="inline-flex items-center gap-2 text-terracotta">
        <strong className="text-2xl font-serif">{total}</strong> flagged
      </span>
      {breakdown.filter((b) => (flags[b.key] || 0) > 0).map((b) => (
        <span key={b.key} className="inline-block text-xs uppercase tracking-wider2 px-2.5 py-1 border border-terracotta/40 bg-mist/60 text-ink/80">
          {flags[b.key]} · {b.label}
        </span>
      ))}
      <span className="ml-auto text-xs text-muted">
        {flags.none || 0} clean
      </span>
    </div>
  );
}
