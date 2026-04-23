import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, FileText, AlertTriangle, Home } from 'lucide-react';
import { useSession } from '../../store/sessionStore';
import { getResults, resultsDownloadUrl, apiErrorMessage } from '../../lib/api';

function Chip({ colour, children }) {
  const cls = {
    navy: 'bg-navy text-white',
    gold: 'bg-gold text-navy',
    terracotta: 'bg-[#b85c38] text-white',
  }[colour || 'gold'];
  return (
    <span className={`inline-block text-[10px] uppercase tracking-wider2 font-medium px-2 py-1 ${cls}`}>
      {children}
    </span>
  );
}

function ScorePill({ score }) {
  const rounded = typeof score === 'number' ? score.toFixed(1) : score;
  return (
    <span className="inline-block text-xs font-medium text-navy border border-navy/30 px-2 py-0.5 ml-2 align-middle">
      {rounded}/5
    </span>
  );
}

function DimensionSection({ profile }) {
  const { name, score, confidence, observed, transformation_relevance, evidence_quotes, band, definition } = profile;
  return (
    <article className="mt-10">
      <h3 className="font-serif text-xl text-navy leading-snug">
        {name}
        <ScorePill score={score} />
        <span className="ml-2 align-middle"><Chip colour={band?.colour}>{band?.category || ''}</Chip></span>
        <span className="ml-2 text-xs uppercase tracking-wider2 text-muted align-middle">
          {confidence} confidence
        </span>
      </h3>
      {definition && (
        <p className="mt-2 text-sm text-ink/70 italic leading-relaxed">{definition}</p>
      )}
      <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">{observed}</p>
      <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">
        <span className="font-medium text-navy">What this means for transformation readiness. </span>
        {transformation_relevance}
      </p>
      {evidence_quotes && evidence_quotes.length > 0 && (
        <div className="mt-4 border-l-2 border-gold pl-4">
          <p className="text-xs uppercase tracking-wider2 text-gold-dark mb-2">Evidence from your responses</p>
          <ul className="space-y-1.5">
            {evidence_quotes.map((q, i) => (
              <li key={i} className="text-[14px] text-ink/75 italic">&ldquo;{q}&rdquo;</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

function CalibrationVisual({ sa }) {
  if (!sa || sa.status !== 'computed') return null;
  const clipped = Math.max(-2, Math.min(2, sa.delta || 0));
  const pct = (clipped + 2) * 25;
  return (
    <div className="mt-6 p-5 bg-mist border-l-2 border-gold">
      <p className="text-sm text-navy font-medium">
        {sa.band}
        <span className="text-ink/60 font-normal"> · Δ = {sa.delta} ({(sa.direction || '').replace('_', '-')})</span>
      </p>
      <div className="mt-3 relative h-2 bg-hairline rounded-sm" aria-hidden="true">
        <div
          className="absolute -top-1 h-4 w-1 bg-navy"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] uppercase tracking-wider2 text-muted">
        <span>Under-claiming</span>
        <span>Well-calibrated</span>
        <span>Over-claiming</span>
      </div>
      <p className="mt-4 text-xs text-ink/70">
        <span className="text-navy font-medium">Claimed:</span> {sa.claimed}
        <span className="mx-3">·</span>
        <span className="text-navy font-medium">Observed:</span> {sa.observed}
      </p>
    </div>
  );
}

export default function Results() {
  const navigate = useNavigate();
  const sessionId = useSession((s) => s.sessionId);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await getResults(sessionId);
        if (cancelled) return;
        setData(r);
      } catch (e) {
        if (cancelled) return;
        // 409 synthesis not yet complete → bounce back to processing
        if (e?.response?.status === 409) {
          navigate('/assessment/processing', { replace: true });
          return;
        }
        setError(apiErrorMessage(e, 'Could not load your results.'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId, navigate]);

  const completedDate = useMemo(() => {
    if (!data?.completed_at) return '';
    try { return new Date(data.completed_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }); }
    catch { return ''; }
  }, [data]);

  if (loading) {
    return <p className="text-sm uppercase tracking-wider2 text-muted">Loading your results…</p>;
  }
  if (error) {
    return (
      <div className="max-w-xl">
        <p className="text-sm text-red-700">{error}</p>
        <button type="button" onClick={() => navigate('/')} className="mt-6 btn-primary">
          Return home <Home className="w-4 h-4" strokeWidth={2} />
        </button>
      </div>
    );
  }
  if (!data) return null;

  // Graceful error path — scoring_error from the synthesis worker
  if (data.status === 'error' || data.scoring_error) {
    return (
      <section className="max-w-xl mx-auto">
        <div className="card card-gold-top">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-navy" strokeWidth={1.75} />
            <span className="eyebrow">Report pending review</span>
          </div>
          <p className="mt-4 text-[15px] text-ink/85 leading-relaxed">
            We couldn’t produce your personalised report automatically. An assessor will review your session
            and reach out.
          </p>
          <p className="mt-3 text-sm text-muted">
            Your resume code <span className="font-mono text-navy">{data?.resume_code || ''}</span> will let
            you return to this page once the report is ready.
          </p>
        </div>
      </section>
    );
  }

  const { deliverable, self_awareness, strategic_scenario_scores, participant, resume_code, dimensions } = data;
  const not_assessed = dimensions?.not_assessed || [];
  const es = deliverable.executive_summary || {};
  const dd = deliverable.ai_fluency_deep_dive || {};
  const ia = deliverable.integration_analysis || {};
  const strategic = strategic_scenario_scores || {};
  const cf = strategic.cognitive_flexibility;
  const st = strategic.systems_thinking;
  const addl = strategic.additional_observations;

  const pdfUrl = resultsDownloadUrl(sessionId, 'pdf');
  const mdUrl = resultsDownloadUrl(sessionId, 'markdown');

  return (
    <section className="max-w-[820px] mx-auto print:max-w-full">
      {/* 1. Cover */}
      <div className="print:mt-0">
        <span className="eyebrow">Executive Assessment</span>
        <h1 className="mt-2 text-3xl sm:text-4xl md:text-5xl font-serif text-navy tracking-tight leading-tight">
          Transformation Readiness Assessment
        </h1>
        <p className="mt-4 text-base text-ink/75">
          <span className="text-navy font-medium">{participant.first_name}</span>
          {participant.organisation ? <span> · {participant.organisation}</span> : null}
          {participant.role ? <span> · {participant.role}</span> : null}
        </p>
        {completedDate && (
          <p className="mt-1 text-sm text-muted italic">Completed {completedDate}</p>
        )}
        <span className="gold-rule block mt-6" aria-hidden="true" />
      </div>

      {/* 2. Executive Summary */}
      <ReportSection n="1" title="Executive Summary">
        <div className="flex items-center gap-3 flex-wrap">
          <Chip colour={es.overall_colour}>{es.overall_category}</Chip>
          <span className="text-sm text-ink/75">{es.category_statement || ''}</span>
        </div>
        <p className="mt-5 text-[15px] text-ink/85 leading-relaxed">{es.prose}</p>

        {es.key_strengths?.length > 0 && (
          <>
            <h3 className="mt-8 eyebrow text-navy">Key strengths</h3>
            <ul className="mt-3 space-y-2">
              {es.key_strengths.map((s, i) => (
                <li key={i} className="text-[15px] text-ink/85 leading-relaxed">
                  <span className="font-medium text-navy">{s.heading}</span> — {s.evidence}
                </li>
              ))}
            </ul>
          </>
        )}

        {es.development_priorities?.length > 0 && (
          <>
            <h3 className="mt-6 eyebrow text-navy">Development priorities</h3>
            <ul className="mt-3 space-y-2">
              {es.development_priorities.map((d, i) => (
                <li key={i} className="text-[15px] text-ink/85 leading-relaxed">
                  <span className="font-medium text-navy">{d.heading}</span> — {d.evidence}
                </li>
              ))}
            </ul>
          </>
        )}

        {es.bottom_line && (
          <p className="mt-6 text-[15px] italic text-ink/80 leading-relaxed">{es.bottom_line}</p>
        )}
      </ReportSection>

      {/* 3. Dimension Profile — Assessed */}
      <ReportSection n="2" title="Dimension Profile — Assessed">
        {(deliverable.dimension_profiles || []).map((p) => (
          <DimensionSection key={p.dimension_id} profile={p} />
        ))}
      </ReportSection>

      {/* 4. Self-Awareness Insight */}
      <ReportSection n="3" title="Self-Awareness Insight">
        {ia.self_awareness_accuracy_narrative && (
          <p className="text-[15px] text-ink/85 leading-relaxed">{ia.self_awareness_accuracy_narrative}</p>
        )}
        <CalibrationVisual sa={self_awareness} />
      </ReportSection>

      {/* 5. AI Fluency Deep Dive */}
      <ReportSection n="4" title="AI Fluency Deep Dive">
        {dd.overview && <p className="text-[15px] text-ink/85 leading-relaxed">{dd.overview}</p>}
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-mist">
                <th className="text-left px-3 py-2 text-xs uppercase tracking-wider2 text-navy font-semibold border-b border-hairline">Component</th>
                <th className="text-left px-3 py-2 text-xs uppercase tracking-wider2 text-navy font-semibold border-b border-hairline">Score</th>
                <th className="text-left px-3 py-2 text-xs uppercase tracking-wider2 text-navy font-semibold border-b border-hairline">Confidence</th>
                <th className="text-left px-3 py-2 text-xs uppercase tracking-wider2 text-navy font-semibold border-b border-hairline">Notes</th>
              </tr>
            </thead>
            <tbody>
              {(dd.components_table || []).map((r, i) => (
                <tr key={i} className="border-b border-hairline">
                  <td className="px-3 py-3 font-medium text-navy">{r.component}</td>
                  <td className="px-3 py-3 text-ink/85">{r.score}/5</td>
                  <td className="px-3 py-3 text-ink/85 capitalize">{r.confidence}</td>
                  <td className="px-3 py-3 text-ink/75">{r.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {dd.what_excellent_looks_like && (
          <p className="mt-5 text-[15px] text-ink/85 leading-relaxed">
            <span className="font-medium text-navy">What excellent looks like. </span>
            {dd.what_excellent_looks_like}
          </p>
        )}
        {dd.participant_gap && (
          <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">
            <span className="font-medium text-navy">This participant&rsquo;s gap. </span>
            {dd.participant_gap}
          </p>
        )}
        {dd.illustrative_quotes?.length > 0 && (
          <div className="mt-5 border-l-2 border-gold pl-4">
            <p className="text-xs uppercase tracking-wider2 text-gold-dark mb-2">Illustrative quotes</p>
            <ul className="space-y-1.5">
              {dd.illustrative_quotes.map((q, i) => (
                <li key={i} className="text-[14px] text-ink/75 italic">&ldquo;{q}&rdquo;</li>
              ))}
            </ul>
          </div>
        )}
      </ReportSection>

      {/* 6. Strategic Decision Profile */}
      <ReportSection n="5" title="Strategic Decision Profile">
        {cf && (
          <div className="mt-2">
            <h3 className="font-serif text-xl text-navy">
              Cognitive Flexibility <ScorePill score={cf.score} />
              <span className="ml-2 text-xs uppercase tracking-wider2 text-muted align-middle">
                {cf.confidence} confidence
              </span>
            </h3>
            <dl className="mt-3 space-y-2 text-[15px] text-ink/85 leading-relaxed">
              <div><dt className="inline text-navy font-medium">Part 1 position. </dt><dd className="inline">{cf.evidence?.part1_position}</dd></div>
              <div><dt className="inline text-navy font-medium">Part 2 revision. </dt><dd className="inline">{cf.evidence?.part2_revision}</dd></div>
              <div><dt className="inline text-navy font-medium">Revision quality. </dt><dd className="inline">{cf.evidence?.revision_quality}</dd></div>
            </dl>
            {cf.evidence?.key_quote && (
              <p className="mt-4 border-l-2 border-gold pl-4 italic text-ink/75">&ldquo;{cf.evidence.key_quote}&rdquo;</p>
            )}
          </div>
        )}
        {st && (
          <div className="mt-8">
            <h3 className="font-serif text-xl text-navy">
              Systems Thinking <ScorePill score={st.score} />
              <span className="ml-2 text-xs uppercase tracking-wider2 text-muted align-middle">
                {st.confidence} confidence
              </span>
            </h3>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <p className="eyebrow text-navy mb-2">Connections identified</p>
                <ul className="list-disc ml-4 space-y-1 text-[14px] text-ink/85">
                  {(st.evidence?.connections_identified || []).map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </div>
              <div>
                <p className="eyebrow text-navy mb-2">Connections missed</p>
                <ul className="list-disc ml-4 space-y-1 text-[14px] text-ink/85">
                  {(st.evidence?.connections_missed || []).map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </div>
            </div>
            {st.evidence?.key_quote && (
              <p className="mt-4 border-l-2 border-gold pl-4 italic text-ink/75">&ldquo;{st.evidence.key_quote}&rdquo;</p>
            )}
          </div>
        )}
        {addl && (
          <div className="mt-8 space-y-3 text-[15px] text-ink/85 leading-relaxed">
            <p><span className="text-navy font-medium">Stakeholder awareness. </span>{addl.stakeholder_awareness}</p>
            <p><span className="text-navy font-medium">Ethical reasoning. </span>{addl.ethical_reasoning}</p>
            <p><span className="text-navy font-medium">Analytical quality. </span>{addl.analytical_quality}</p>
          </div>
        )}
      </ReportSection>

      {/* 7. Development Recommendations */}
      <ReportSection n="6" title="Development Recommendations">
        {(deliverable.development_recommendations || []).map((r, i) => (
          <article key={i} className="mt-6">
            <h3 className="font-serif text-lg text-navy">{i + 1}. {r.title}</h3>
            <dl className="mt-2 space-y-1.5 text-[15px] text-ink/85 leading-relaxed">
              <div><dt className="inline text-navy font-medium">What: </dt><dd className="inline">{r.what}</dd></div>
              <div><dt className="inline text-navy font-medium">Why: </dt><dd className="inline">{r.why}</dd></div>
              <div><dt className="inline text-navy font-medium">How: </dt><dd className="inline">{r.how}</dd></div>
              <div><dt className="inline text-navy font-medium">Expectation: </dt><dd className="inline">{r.expectation}</dd></div>
            </dl>
          </article>
        ))}
      </ReportSection>

      {/* 8. Integration Analysis */}
      <ReportSection n="7" title="Integration Analysis">
        {ia.patterns && <p className="text-[15px] text-ink/85 leading-relaxed">{ia.patterns}</p>}
        {ia.contradictions && (
          <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">
            <span className="text-navy font-medium">Contradictions. </span>{ia.contradictions}
          </p>
        )}
        {ia.emergent_themes && (
          <p className="mt-3 text-[15px] text-ink/85 leading-relaxed">
            <span className="text-navy font-medium">Emergent themes. </span>{ia.emergent_themes}
          </p>
        )}
      </ReportSection>

      {/* 9. Methodology + Not-assessed */}
      <ReportSection n="8" title="Methodology Note">
        <p className="text-[15px] text-ink/85 leading-relaxed">{deliverable.methodology_note}</p>

        <h3 className="mt-8 eyebrow text-navy">Not assessed in this preview</h3>
        <p className="mt-2 text-sm italic text-ink/60 leading-relaxed">
          The full framework covers 16 dimensions. The following ten were not assessed in this demonstration
          and would be covered in a production assessment.
        </p>
        <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-5">
          {not_assessed.map((d) => (
            <div key={d.id} className="text-sm leading-relaxed">
              <p className="text-[10px] uppercase tracking-wider2 text-muted">{d.cluster}</p>
              <p className="font-medium text-navy">{d.name}</p>
              <p className="text-ink/70">{d.definition}</p>
            </div>
          ))}
        </div>
      </ReportSection>

      {/* 10. Downloads + footer */}
      <div className="mt-16 pt-8 border-t border-hairline print:hidden">
        <h3 className="eyebrow text-navy">Download your report</h3>
        <div className="mt-4 flex flex-wrap gap-4">
          <a href={pdfUrl} className="btn-primary" aria-label="Download PDF report">
            <Download className="w-4 h-4" strokeWidth={2} /> Download PDF
          </a>
          <a href={mdUrl} className="btn-ghost" aria-label="Download Markdown report">
            <FileText className="w-4 h-4" strokeWidth={2} /> Download Markdown
          </a>
        </div>
        <p className="mt-6 text-xs text-muted">
          Your report has been saved. You can return using your resume code:{' '}
          <span className="font-mono text-navy">{resume_code}</span>.
        </p>
        <p className="mt-1 text-xs text-muted">This deliverable will be retained for 60 days.</p>
      </div>
    </section>
  );
}

function ReportSection({ n, title, children }) {
  return (
    <section className="mt-14" id={`section-${n}`}>
      <div className="flex items-baseline gap-4">
        <span className="eyebrow">Section {n}</span>
        <h2 className="font-serif text-2xl md:text-3xl text-navy tracking-tight">{title}</h2>
      </div>
      <span className="gold-rule block mt-4" aria-hidden="true" />
      <div className="mt-6">{children}</div>
    </section>
  );
}
