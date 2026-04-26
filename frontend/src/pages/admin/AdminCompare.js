import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, Printer } from 'lucide-react';
import { compareSessions, apiErrorMessage } from '../../lib/adminApi';
import ScoreChip from '../../components/admin/ScoreChip';

// Phase 11A — side-by-side comparison report. Reads /api/admin/sessions/compare,
// renders a 9-section single-page report, prints cleanly to A4 portrait.

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
function fmtDelta(d) {
  if (d === null || d === undefined) return '—';
  const sign = d > 0 ? '+' : d < 0 ? '−' : '';
  return `${sign}${Math.abs(d).toFixed(1)}`;
}

// -------------------------------------------------------------------------- //
// Overlaid radar — both participants on the same axes.
// Uses the same axis order, viewBox, and label-anchor logic as the admin
// AdminSessionDetail RadarChart so the visual reads as the same chart family.
// -------------------------------------------------------------------------- //
function OverlaidRadar({ axisOrder, radarData, participants }) {
  const size = 220, cx = size / 2, cy = size / 2, r = 82;
  const LABEL_R = r + 18;
  const VB_X = -100, VB_Y = -40, VB_W = size + 200, VB_H = size + 80;

  const axes = axisOrder.map((id, i) => {
    const angle = (-Math.PI / 2) + (i / axisOrder.length) * Math.PI * 2;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    const labelX = cx + LABEL_R * Math.cos(angle);
    const labelY = cy + LABEL_R * Math.sin(angle);
    const words = id.replace(/_/g, ' ').split(' ');
    const lines = words.length <= 1
      ? [words[0]]
      : words.length === 2
        ? [words[0], words[1]]
        : [words.slice(0, words.length - 1).join(' '), words[words.length - 1]];
    return { id, angle, x, y, labelX, labelY, lines };
  });

  function polyFor(seriesIdx) {
    const dims = (radarData[seriesIdx] || {}).dimensions || {};
    return axes.map((a) => {
      const score = Number(dims[a.id]) || 0;
      const sx = cx + (score / 5) * r * Math.cos(a.angle);
      const sy = cy + (score / 5) * r * Math.sin(a.angle);
      return `${sx},${sy}`;
    }).join(' ');
  }

  const a = participants[0]?.name || 'Participant A';
  const b = participants[1]?.name || 'Participant B';

  return (
    <div>
      <svg
        width="100%" height="auto"
        viewBox={`${VB_X} ${VB_Y} ${VB_W} ${VB_H}`}
        role="img" aria-labelledby="cmp-radar-title cmp-radar-desc"
        style={{ maxWidth: 480 }}
      >
        <title id="cmp-radar-title">Overlaid dimension radar</title>
        <desc id="cmp-radar-desc">{`Radar chart overlaying ${a} (navy) and ${b} (gold) across six leadership-readiness dimensions.`}</desc>

        {/* concentric rings */}
        {[0.25, 0.5, 0.75, 1.0].map((scale, i) => (
          <polygon
            key={i}
            points={axes.map((ax) => `${cx + scale * r * Math.cos(ax.angle)},${cy + scale * r * Math.sin(ax.angle)}`).join(' ')}
            fill="none" stroke="#1e3a5f" strokeOpacity={0.10}
          />
        ))}
        {/* axis lines */}
        {axes.map((ax) => (
          <line key={ax.id} x1={cx} y1={cy} x2={ax.x} y2={ax.y}
                stroke="#1e3a5f" strokeOpacity={0.15} />
        ))}

        {/* B (gold) drawn first so navy overlays cleanly */}
        <polygon points={polyFor(1)} fill="#d4a84b" fillOpacity={0.30} stroke="#b88a2a" strokeWidth={1.4} />
        {/* A (navy) on top */}
        <polygon points={polyFor(0)} fill="#1e3a5f" fillOpacity={0.30} stroke="#1e3a5f" strokeWidth={1.4} />

        {/* score dots — small circles per axis per participant */}
        {axes.map((ax) => {
          const scA = Number(((radarData[0] || {}).dimensions || {})[ax.id]) || 0;
          const scB = Number(((radarData[1] || {}).dimensions || {})[ax.id]) || 0;
          return (
            <g key={`${ax.id}-dots`}>
              <circle cx={cx + (scA / 5) * r * Math.cos(ax.angle)} cy={cy + (scA / 5) * r * Math.sin(ax.angle)} r={2.5} fill="#1e3a5f" />
              <circle cx={cx + (scB / 5) * r * Math.cos(ax.angle)} cy={cy + (scB / 5) * r * Math.sin(ax.angle)} r={2.5} fill="#b88a2a" />
            </g>
          );
        })}

        {/* axis labels */}
        {axes.map((ax) => {
          const anchor = Math.cos(ax.angle) > 0.15 ? 'start'
                       : Math.cos(ax.angle) < -0.15 ? 'end'
                       : 'middle';
          const lineHeight = 9;
          const startDy = ax.lines.length === 2 ? -lineHeight / 2 : 0;
          return (
            <text key={`${ax.id}-l`} x={ax.labelX} y={ax.labelY} fontSize="8.5" fill="#6b7280"
                  textAnchor={anchor} dominantBaseline="middle"
                  letterSpacing="1" style={{ textTransform: 'uppercase' }}>
              {ax.lines.map((line, idx) => (
                <tspan key={idx} x={ax.labelX} dy={idx === 0 ? startDy : lineHeight}>{line}</tspan>
              ))}
            </text>
          );
        })}
      </svg>

      <div className="mt-3 flex items-center justify-center gap-6 text-xs text-ink/80">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-3 h-3" style={{ background: '#1e3a5f', opacity: 0.6 }} />
          {a}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-3 h-3" style={{ background: '#d4a84b', opacity: 0.7 }} />
          {b}
        </span>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------------- //
// Page
// -------------------------------------------------------------------------- //
export default function AdminCompare() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const idsParam = searchParams.get('ids') || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const ids = useMemo(() => idsParam.split(',').map((s) => s.trim()).filter(Boolean), [idsParam]);

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true); setError(null); setData(null);
      if (ids.length !== 2) {
        setError('Comparison requires exactly two session ids.');
        setLoading(false);
        return;
      }
      try {
        const d = await compareSessions(ids[0], ids[1]);
        if (alive) setData(d);
      } catch (e) {
        if (alive) {
          // Surface validation reasons if the backend returned a structured 422.
          const detail = e?.response?.data?.detail;
          if (detail && typeof detail === 'object' && Array.isArray(detail.incomplete)) {
            const reasons = detail.incomplete.map((x) => `${x.session_id.slice(0, 8)}… (${x.reasons.join(', ')})`).join(' · ');
            setError(`${detail.message} ${reasons}`);
          } else {
            setError(apiErrorMessage(e, 'Could not load comparison.'));
          }
        }
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => { alive = false; };
  }, [idsParam]);

  if (loading) {
    return (
      <section>
        <p className="text-muted italic">Loading comparison…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section>
        <div className="bg-white border border-terracotta/40 p-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-terracotta mt-0.5 flex-shrink-0" />
            <div>
              <h1 className="font-serif text-xl text-navy">Comparison unavailable</h1>
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

  const [pA, pB] = data.participants;
  const [esA, esB] = data.executive_summaries;
  const [kqA, kqB] = data.key_quotes;
  const [scA, scB] = data.scenario_quotes;
  const flagsActive = (data.flags || []).some((f) => f.response_pattern_flag || f.scoring_error);

  return (
    <section className="cmp-print">
      {/* Print stylesheet — keeps radar atomic, hides nav chrome on paper */}
      <style>{`
        @media print {
          @page { size: A4 portrait; margin: 14mm; }
          .cmp-no-print { display: none !important; }
          .cmp-print h2 { page-break-after: avoid; }
          .cmp-section { page-break-inside: avoid; }
          .cmp-radar { page-break-inside: avoid; break-inside: avoid; }
          body { background: #ffffff !important; }
        }
      `}</style>

      {/* 1. Header strip */}
      <div className="cmp-section flex items-start justify-between mb-6">
        <div>
          <span className="eyebrow">Admin · Comparison</span>
          <h1 className="mt-1 font-serif text-3xl md:text-4xl text-navy tracking-tight">Session Comparison</h1>
          <p className="mt-2 text-sm text-muted">
            <strong className="text-ink/90">{pA?.name || '—'}</strong>
            <span className="mx-2 text-gold">·</span>
            <strong className="text-ink/90">{pB?.name || '—'}</strong>
            <span className="ml-3 text-muted">
              {fmtDate(pA?.completion_date)} <span className="mx-1">/</span> {fmtDate(pB?.completion_date)}
            </span>
          </p>
        </div>
        <div className="cmp-no-print flex items-center gap-3">
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

      {/* 2. Twin cover row */}
      <div className="cmp-section grid grid-cols-1 md:grid-cols-2 gap-5 mb-8">
        {[pA, pB].map((p, i) => (
          <div key={p?.session_id || i} className="bg-white border border-hairline border-t-[3px] border-t-navy p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="eyebrow">Participant {i === 0 ? 'A' : 'B'}</div>
                <h2 className="mt-1 font-serif text-xl text-navy">{p?.name || '—'}</h2>
                <p className="mt-1 text-sm text-ink/70">
                  {p?.role || '—'}{p?.organisation ? ` · ${p.organisation}` : ''}
                </p>
                <p className="mt-1 text-xs text-muted">Completed {fmtDate(p?.completion_date)}</p>
              </div>
              <div className="text-right">
                <ScoreChip colour={p?.overall_colour}>{p?.overall_category || '—'}</ScoreChip>
                {p?.response_pattern_flag && (
                  <div className="mt-2 inline-block text-[10px] uppercase tracking-wider2 text-terracotta border border-terracotta/40 px-2 py-0.5">
                    {String(p.response_pattern_flag).replace(/_/g, ' ')}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 3. Overlaid radar */}
      <div className="cmp-section cmp-radar bg-white border border-hairline p-6 mb-8">
        <h2 className="font-serif text-xl text-navy mb-4">Dimension overlay</h2>
        <div className="flex items-center justify-center">
          <OverlaidRadar
            axisOrder={data.axis_order || []}
            radarData={data.radar_data || []}
            participants={data.participants || []}
          />
        </div>
      </div>

      {/* 4. Dimension comparison table */}
      <div className="cmp-section bg-white border border-hairline p-6 mb-8 overflow-x-auto">
        <h2 className="font-serif text-xl text-navy mb-4">Dimension comparison</h2>
        <p className="text-xs text-muted mb-3">Sorted by absolute difference. <span className="text-terracotta">Significant divergence</span> = score band gap of 1.0+.</p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider2 text-muted border-b border-hairline">
              <th scope="col" className="text-left px-3 py-2 font-medium">Dimension</th>
              <th scope="col" className="text-left px-3 py-2 font-medium">{pA?.name || 'A'}</th>
              <th scope="col" className="text-left px-3 py-2 font-medium">{pB?.name || 'B'}</th>
              <th scope="col" className="text-left px-3 py-2 font-medium">Δ</th>
              <th scope="col" className="text-left px-3 py-2 font-medium">Notes</th>
            </tr>
          </thead>
          <tbody>
            {(data.dimension_table || []).map((row) => (
              <tr key={row.dimension_id} className="border-b border-hairline">
                <td className="px-3 py-2.5 text-navy font-medium">{row.dimension}</td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className="mr-2">{fmtScore(row.a_score)}</span>
                  {row.a_band && <span className="text-[10px] uppercase tracking-wider2 text-muted">{row.a_band}</span>}
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className="mr-2">{fmtScore(row.b_score)}</span>
                  {row.b_band && <span className="text-[10px] uppercase tracking-wider2 text-muted">{row.b_band}</span>}
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className={
                    row.delta === null ? 'text-muted'
                    : row.delta > 0 ? 'text-navy font-medium'
                    : row.delta < 0 ? 'text-terracotta font-medium'
                    : 'text-muted'
                  }>{fmtDelta(row.delta)}</span>
                </td>
                <td className="px-3 py-2.5 text-xs">
                  {row.divergent
                    ? <span className="text-terracotta">Significant divergence</span>
                    : <span className="text-muted">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 5. Executive summaries side-by-side */}
      <div className="cmp-section grid grid-cols-1 md:grid-cols-2 gap-5 mb-8">
        {[esA, esB].map((es, i) => (
          <div key={i} className="bg-white border border-hairline p-5">
            <div className="flex items-start justify-between gap-2 mb-3">
              <h2 className="font-serif text-lg text-navy">Executive summary — {i === 0 ? pA?.name : pB?.name}</h2>
              <ScoreChip colour={es?.overall_colour} size="sm">{es?.overall_category || '—'}</ScoreChip>
            </div>
            {es?.category_statement && (
              <p className="text-sm text-ink/80 italic mb-2">{es.category_statement}</p>
            )}
            {es?.prose && (
              <p className="text-sm text-ink/80 whitespace-pre-line">{es.prose}</p>
            )}
            {es?.bottom_line && (
              <p className="text-sm text-ink/90 mt-3 pt-3 border-t border-hairline/70 italic">
                <strong className="not-italic text-navy">Bottom line:</strong> {es.bottom_line}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* 6. AI Fluency evidence */}
      <div className="cmp-section bg-white border border-hairline p-6 mb-8">
        <h2 className="font-serif text-xl text-navy mb-2">AI Fluency evidence</h2>
        <p className="text-xs text-muted mb-4">Verbatim quotes from each participant&apos;s AI Fluency Discussion.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {[kqA, kqB].map((kq, i) => (
            <div key={i}>
              <div className="eyebrow text-muted mb-2">{i === 0 ? pA?.name : pB?.name}</div>
              {(kq?.quotes || []).length === 0 ? (
                <p className="text-sm text-muted italic">No quotes available.</p>
              ) : (
                <ul className="space-y-3">
                  {kq.quotes.map((q, j) => (
                    <li key={j} className="border-l-2 border-gold pl-3 text-sm text-ink/80 italic">“{q}”</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 7. Strategic Decision profile */}
      <div className="cmp-section bg-white border border-hairline p-6 mb-8">
        <h2 className="font-serif text-xl text-navy mb-4">Strategic decision profile</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {[scA, scB].map((sc, i) => (
            <div key={i} className="space-y-4">
              <div className="eyebrow text-muted">{i === 0 ? pA?.name : pB?.name}</div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-navy">Cognitive Flexibility</span>
                  <span className="tabular-nums text-sm">
                    {fmtScore(sc?.cognitive_flexibility?.score)}
                    {sc?.cognitive_flexibility?.band && (
                      <span className="ml-2 text-[10px] uppercase tracking-wider2 text-muted">{sc.cognitive_flexibility.band}</span>
                    )}
                  </span>
                </div>
                {sc?.cognitive_flexibility?.key_quote && (
                  <p className="text-sm text-ink/80 italic border-l-2 border-navy pl-3">“{sc.cognitive_flexibility.key_quote}”</p>
                )}
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-navy">Systems Thinking</span>
                  <span className="tabular-nums text-sm">
                    {fmtScore(sc?.systems_thinking?.score)}
                    {sc?.systems_thinking?.band && (
                      <span className="ml-2 text-[10px] uppercase tracking-wider2 text-muted">{sc.systems_thinking.band}</span>
                    )}
                  </span>
                </div>
                {sc?.systems_thinking?.key_quote && (
                  <p className="text-sm text-ink/80 italic border-l-2 border-navy pl-3">“{sc.systems_thinking.key_quote}”</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 8. Caveats / flags */}
      {flagsActive && (
        <div className="cmp-section bg-mist/60 border border-terracotta/30 p-4 mb-8">
          <h2 className="font-serif text-sm text-terracotta mb-2 inline-flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> Caveats
          </h2>
          <ul className="text-xs text-ink/80 space-y-1">
            {(data.flags || []).map((f, i) => {
              const name = i === 0 ? (pA?.name || 'A') : (pB?.name || 'B');
              const bits = [];
              if (f.response_pattern_flag) bits.push(`response pattern: ${String(f.response_pattern_flag).replace(/_/g, ' ')}`);
              if (f.scoring_error) bits.push('scoring error in deliverable');
              if (!bits.length) return null;
              return <li key={i}><strong className="text-navy">{name}:</strong> {bits.join(' · ')}</li>;
            })}
          </ul>
        </div>
      )}

      {/* 9. Footer */}
      <div className="cmp-section flex items-center justify-between text-xs text-muted pt-4 border-t border-hairline">
        <span>Comparison generated {fmtDate(data.generated_at)}.</span>
        <button
          type="button"
          onClick={() => navigate('/admin/sessions')}
          className="cmp-no-print text-navy hover:text-gold inline-flex items-center gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to sessions
        </button>
      </div>
    </section>
  );
}
