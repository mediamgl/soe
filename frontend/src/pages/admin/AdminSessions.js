import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search, ChevronLeft, ChevronRight, Lock, Archive, ArchiveRestore, Trash2,
  RotateCcw, MoreHorizontal, Sliders, X as IconX, GitCompare, Users, Info,
} from 'lucide-react';
import {
  listSessions, patchSession, softDeleteSession, restoreSession, apiErrorMessage,
} from '../../lib/adminApi';
import ScoreChip from '../../components/admin/ScoreChip';

const STATUS_OPTIONS = ['active', 'completed', 'failed', 'abandoned'];

// Phase 11A — dimension filtering / sorting.
const DIMENSIONS = [
  { id: 'learning_agility',          label: 'Learning Agility' },
  { id: 'tolerance_for_ambiguity',   label: 'Tolerance for Ambiguity' },
  { id: 'cognitive_flexibility',     label: 'Cognitive Flexibility' },
  { id: 'self_awareness_accuracy',   label: 'Self-Awareness Accuracy' },
  { id: 'ai_fluency',                label: 'AI Fluency' },
  { id: 'systems_thinking',          label: 'Systems Thinking' },
];
const CATEGORY_OPTIONS = [
  'Transformation Ready',
  'High Potential',
  'Development Required',
  'Limited Readiness',
];
const RESPONSE_FLAG_OPTIONS = [
  { value: '',                       label: 'All' },
  { value: 'any',                    label: 'Any flagged' },
  { value: 'none',                   label: 'None (clean)' },
  { value: 'high_acquiescence',      label: 'High acquiescence' },
  { value: 'low_variance',           label: 'Low variance' },
  { value: 'extreme_response_bias',  label: 'Extreme bias' },
];
const SORT_OPTIONS = [
  { value: '-created_at',            label: 'Newest first' },
  { value: 'created_at',             label: 'Oldest first' },
  { value: '-completed_at',          label: 'Recently completed' },
  { value: 'participant.name',       label: 'Name A–Z' },
  // Dimension sorts (Phase 11A)
  ...DIMENSIONS.flatMap((d) => ([
    { value: `-${d.id}`, label: `${d.label} (high → low)` },
    { value: d.id,       label: `${d.label} (low → high)` },
  ])),
];

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return iso.slice(0, 10); }
}
function fmtDuration(sec) {
  if (!sec && sec !== 0) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
}
function fmtScore(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return n.toFixed(1);
}
function isSessionCompleteForCompare(row) {
  // Comparison requires a completed session with a populated deliverable.
  return row.status === 'completed' && !!row.overall_category && !row.has_scoring_error;
}

export default function AdminSessions() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // --- URL-driven filter state (Phase 11A: deep-linkable filters) ---
  const initialState = useMemo(() => {
    const dimMin = {};
    const dimMax = {};
    for (const [k, v] of searchParams.entries()) {
      const mMin = k.match(/^dimension_min\[(\w+)\]$/);
      const mMax = k.match(/^dimension_max\[(\w+)\]$/);
      if (mMin) dimMin[mMin[1]] = v;
      else if (mMax) dimMax[mMax[1]] = v;
    }
    return {
      q: searchParams.get('q') || '',
      sort: searchParams.get('sort') || '-created_at',
      page: Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1),
      statusFilter: (searchParams.get('status') || '').split(',').filter(Boolean),
      archivedFilter: searchParams.get('archived') || '',
      includeDeleted: searchParams.get('include_deleted') !== 'false',
      categoryFilter: (searchParams.get('overall_category') || '').split(',').filter(Boolean),
      responseFlag: searchParams.get('response_flag') || '',
      dateFrom: searchParams.get('date_from') || '',
      dateTo: searchParams.get('date_to') || '',
      dimMin,
      dimMax,
    };
  }, []); // mount-only; subsequent URL writes go via setSearchParams below.

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(initialState.page);
  const [pageSize] = useState(25);
  const [q, setQ] = useState(initialState.q);
  const [statusFilter, setStatusFilter] = useState(initialState.statusFilter);
  const [archivedFilter, setArchivedFilter] = useState(initialState.archivedFilter);
  const [includeDeleted, setIncludeDeleted] = useState(initialState.includeDeleted);
  const [sort, setSort] = useState(initialState.sort);
  const [categoryFilter, setCategoryFilter] = useState(initialState.categoryFilter);
  const [responseFlag, setResponseFlag] = useState(initialState.responseFlag);
  const [dateFrom, setDateFrom] = useState(initialState.dateFrom);
  const [dateTo, setDateTo] = useState(initialState.dateTo);
  const [dimMin, setDimMin] = useState(initialState.dimMin);   // { learning_agility: '3.5', ... }
  const [dimMax, setDimMax] = useState(initialState.dimMax);

  // Date range validation — if both are set, From must be ≤ To. Invalid range
  // suppresses the API call so the list doesn't show stale results.
  const dateRangeError = useMemo(() => {
    if (dateFrom && dateTo && dateFrom > dateTo) {
      return 'From date must be on or before To date.';
    }
    return null;
  }, [dateFrom, dateTo]);

  const [dimPanelOpen, setDimPanelOpen] = useState(
    Object.keys(initialState.dimMin).length + Object.keys(initialState.dimMax).length > 0
  );
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionPending, setActionPending] = useState(null);
  const [menuOpenFor, setMenuOpenFor] = useState(null);
  const debounceRef = useRef(null);

  // ---- URL <-> state sync (write only; read happens on mount).
  useEffect(() => {
    const next = new URLSearchParams();
    if (q.trim()) next.set('q', q.trim());
    if (sort && sort !== '-created_at') next.set('sort', sort);
    if (page > 1) next.set('page', String(page));
    if (statusFilter.length) next.set('status', statusFilter.join(','));
    if (archivedFilter) next.set('archived', archivedFilter);
    if (!includeDeleted) next.set('include_deleted', 'false');
    if (categoryFilter.length) next.set('overall_category', categoryFilter.join(','));
    if (responseFlag) next.set('response_flag', responseFlag);
    if (dateFrom) next.set('date_from', dateFrom);
    if (dateTo) next.set('date_to', dateTo);
    for (const [dim, v] of Object.entries(dimMin)) {
      if (v !== '' && v !== null && v !== undefined) next.set(`dimension_min[${dim}]`, String(v));
    }
    for (const [dim, v] of Object.entries(dimMax)) {
      if (v !== '' && v !== null && v !== undefined) next.set(`dimension_max[${dim}]`, String(v));
    }
    setSearchParams(next, { replace: true });
  }, [q, sort, page, statusFilter, archivedFilter, includeDeleted, categoryFilter, responseFlag, dateFrom, dateTo, dimMin, dimMax, setSearchParams]);

  // ---- Active filter chips (visible above the dim panel content).
  const activeChips = useMemo(() => {
    const out = [];
    if (dateFrom || dateTo) {
      const label = dateFrom && dateTo ? `Created ${dateFrom} → ${dateTo}`
                  : dateFrom            ? `Created from ${dateFrom}`
                                        : `Created up to ${dateTo}`;
      out.push({ key: 'date-range', label, kind: 'date' });
    }
    for (const d of DIMENSIONS) {
      if (dimMin[d.id]) out.push({ key: `min-${d.id}`, label: `${d.label} ≥ ${dimMin[d.id]}`, kind: 'min', dim: d.id });
      if (dimMax[d.id]) out.push({ key: `max-${d.id}`, label: `${d.label} ≤ ${dimMax[d.id]}`, kind: 'max', dim: d.id });
    }
    for (const c of categoryFilter) out.push({ key: `cat-${c}`, label: `Category: ${c}`, kind: 'cat', dim: c });
    if (responseFlag) {
      const opt = RESPONSE_FLAG_OPTIONS.find((o) => o.value === responseFlag);
      out.push({ key: `flag-${responseFlag}`, label: `Flag: ${opt ? opt.label : responseFlag}`, kind: 'flag' });
    }
    return out;
  }, [dimMin, dimMax, categoryFilter, responseFlag, dateFrom, dateTo]);

  function clearChip(c) {
    if (c.kind === 'min') setDimMin((p) => { const n = { ...p }; delete n[c.dim]; return n; });
    else if (c.kind === 'max') setDimMax((p) => { const n = { ...p }; delete n[c.dim]; return n; });
    else if (c.kind === 'cat') setCategoryFilter((p) => p.filter((x) => x !== c.dim));
    else if (c.kind === 'flag') setResponseFlag('');
    else if (c.kind === 'date') { setDateFrom(''); setDateTo(''); }
    setPage(1);
  }
  function clearAllFilters() {
    setDimMin({}); setDimMax({});
    setCategoryFilter([]);
    setResponseFlag('');
    setStatusFilter([]);
    setArchivedFilter('');
    setDateFrom(''); setDateTo('');
    setQ('');
    setPage(1);
  }

  const load = useCallback(async () => {
    // Suppress the API call if the date range is invalid — show the inline
    // error instead of stale data.
    if (dateRangeError) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = {
        page, page_size: pageSize, sort,
        include_deleted: includeDeleted,
      };
      if (q.trim()) params.q = q.trim();
      if (statusFilter.length) params.status = statusFilter.join(',');
      if (archivedFilter) params.archived = archivedFilter;
      if (categoryFilter.length) params.overall_category = categoryFilter.join(',');
      if (responseFlag) params.response_flag = responseFlag;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      // Coerce string inputs to numbers (or skip empty ones).
      const dmin = {}, dmax = {};
      for (const [k, v] of Object.entries(dimMin)) {
        if (v !== '' && !Number.isNaN(Number(v))) dmin[k] = Number(v);
      }
      for (const [k, v] of Object.entries(dimMax)) {
        if (v !== '' && !Number.isNaN(Number(v))) dmax[k] = Number(v);
      }
      if (Object.keys(dmin).length) params.dimension_min = dmin;
      if (Object.keys(dmax).length) params.dimension_max = dmax;
      const data = await listSessions(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(apiErrorMessage(e, 'Could not load sessions.'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, sort, q, statusFilter, archivedFilter, includeDeleted, categoryFilter, responseFlag, dateFrom, dateTo, dimMin, dimMax, dateRangeError]);

  // Debounce — re-load 300 ms after the last filter mutation
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(load, 300);
    return () => clearTimeout(debounceRef.current);
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const toggleStatus = (s) => {
    setStatusFilter((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]);
    setPage(1);
  };
  const toggleCategory = (c) => {
    setCategoryFilter((prev) => prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]);
    setPage(1);
  };

  // ---- Bulk-select handling ----
  const toggleSelect = (row) => {
    if (!isSessionCompleteForCompare(row)) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(row.session_id)) next.delete(row.session_id);
      else next.add(row.session_id);
      return next;
    });
  };
  const clearSelection = () => setSelectedIds(new Set());
  const onCompare = () => {
    if (selectedIds.size !== 2) return;
    const ids = Array.from(selectedIds);
    navigate(`/admin/compare?ids=${encodeURIComponent(ids.join(','))}`);
  };
  const onCohort = () => {
    if (selectedIds.size < 2) return;
    const ids = Array.from(selectedIds);
    navigate(`/admin/cohort?ids=${encodeURIComponent(ids.join(','))}`);
  };

  async function onArchiveToggle(row) {
    setActionPending(row.session_id);
    setMenuOpenFor(null);
    try {
      await patchSession(row.session_id, { archived: !row.archived });
      await load();
    } catch (e) {
      alert(apiErrorMessage(e, 'Action failed.'));
    } finally {
      setActionPending(null);
    }
  }
  async function onSoftDelete(row) {
    if (!window.confirm(`Soft-delete session for ${row.participant?.name || row.session_id.slice(0, 8)}? PII will be scrubbed; scores and transcripts remain. Restoration is possible for 30 days.`)) return;
    setActionPending(row.session_id); setMenuOpenFor(null);
    try { await softDeleteSession(row.session_id); await load(); }
    catch (e) { alert(apiErrorMessage(e, 'Action failed.')); }
    finally { setActionPending(null); }
  }
  async function onRestore(row) {
    setActionPending(row.session_id); setMenuOpenFor(null);
    try { await restoreSession(row.session_id); await load(); }
    catch (e) { alert(apiErrorMessage(e, 'Restore failed.')); }
    finally { setActionPending(null); }
  }

  // -------------------------------------------------------------------- //
  // Render
  // -------------------------------------------------------------------- //
  return (
    <section>
      <div className="flex items-start justify-between mb-6">
        <div>
          <span className="eyebrow">Admin</span>
          <h1 className="mt-1 font-serif text-3xl md:text-4xl text-navy tracking-tight">Sessions</h1>
          <p className="mt-2 text-sm text-muted">{total.toLocaleString()} total</p>
        </div>
      </div>

      {/* Filter bar */}
      <div className="bg-white border border-hairline p-4 mb-5 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[260px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" strokeWidth={2} />
            <input
              type="text"
              value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              placeholder="Search name, email, organisation, or session id"
              className="form-input pl-10 py-2.5 text-sm"
              aria-label="Search sessions"
            />
          </div>
          <select
            value={sort}
            onChange={(e) => { setSort(e.target.value); setPage(1); }}
            className="form-input py-2.5 text-sm max-w-[260px]"
            aria-label="Sort sessions"
          >
            {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="eyebrow text-muted">Status:</span>
            {STATUS_OPTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => toggleStatus(s)}
                aria-pressed={statusFilter.includes(s)}
                className={
                  'text-xs uppercase tracking-wider2 px-2.5 py-1 border ' +
                  (statusFilter.includes(s)
                    ? 'border-navy bg-navy text-white'
                    : 'border-hairline text-ink/70 hover:border-navy/30')
                }
              >{s}</button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="eyebrow text-muted">Archived:</span>
            <select
              value={archivedFilter}
              onChange={(e) => { setArchivedFilter(e.target.value); setPage(1); }}
              className="form-input py-1.5 text-xs max-w-[150px]"
              aria-label="Archived filter"
            >
              <option value="">All</option>
              <option value="only">Only archived</option>
              <option value="exclude">Hide archived</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-xs text-ink/75">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => { setIncludeDeleted(e.target.checked); setPage(1); }}
              className="w-4 h-4 accent-navy"
            />
            Show soft-deleted
          </label>
        </div>

        {/* ---- Phase 11A.1: Date range filter (created_at) ---- */}
        <div className="flex flex-wrap items-center gap-4 text-sm pt-2 border-t border-hairline/70">
          <div className="flex items-center gap-2">
            <span className="eyebrow text-muted">Created:</span>
            <label className="flex items-center gap-1 text-xs text-ink/75">
              <span className="text-muted">From</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
                className="form-input py-1 px-2 text-xs"
                aria-label="Created from date"
                aria-invalid={dateRangeError ? 'true' : 'false'}
                aria-describedby={dateRangeError ? 'date-range-error' : undefined}
                max={dateTo || undefined}
              />
            </label>
            <label className="flex items-center gap-1 text-xs text-ink/75">
              <span className="text-muted">To</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
                className="form-input py-1 px-2 text-xs"
                aria-label="Created to date"
                aria-invalid={dateRangeError ? 'true' : 'false'}
                aria-describedby={dateRangeError ? 'date-range-error' : undefined}
                min={dateFrom || undefined}
              />
            </label>
            {(dateFrom || dateTo) && (
              <button
                type="button"
                onClick={() => { setDateFrom(''); setDateTo(''); setPage(1); }}
                className="text-[10px] uppercase tracking-wider2 text-muted hover:text-terracotta"
                aria-label="Clear date range"
              >Clear</button>
            )}
          </div>
        </div>
        {dateRangeError && (
          <p id="date-range-error" role="alert" className="text-xs text-terracotta -mt-1">
            {dateRangeError}
          </p>
        )}

        {/* ---- Phase 11A: Category + Response flag row ---- */}
        <div className="flex flex-wrap items-center gap-4 text-sm pt-2 border-t border-hairline/70">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="eyebrow text-muted">Category:</span>
            {CATEGORY_OPTIONS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => toggleCategory(c)}
                aria-pressed={categoryFilter.includes(c)}
                className={
                  'text-xs uppercase tracking-wider2 px-2.5 py-1 border ' +
                  (categoryFilter.includes(c)
                    ? 'border-gold-dark bg-gold/15 text-navy'
                    : 'border-hairline text-ink/70 hover:border-gold/40')
                }
              >{c}</button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="eyebrow text-muted">Response flag:</span>
            <select
              value={responseFlag}
              onChange={(e) => { setResponseFlag(e.target.value); setPage(1); }}
              className="form-input py-1.5 text-xs max-w-[200px]"
              aria-label="Response flag filter"
            >
              {RESPONSE_FLAG_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {/* ---- Phase 11A: Dimension filters panel ---- */}
        <div className="pt-2 border-t border-hairline/70">
          <button
            type="button"
            onClick={() => setDimPanelOpen((v) => !v)}
            className="inline-flex items-center gap-2 text-xs uppercase tracking-wider2 text-navy hover:text-gold-dark"
            aria-expanded={dimPanelOpen}
            aria-controls="dim-filter-panel"
          >
            <Sliders className="w-4 h-4" />
            Dimension filters
            <span className="text-muted normal-case tracking-normal">
              ({activeChips.length ? `${activeChips.length} active` : 'min/max per dimension'})
            </span>
          </button>

          {/* Active chips */}
          {activeChips.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {activeChips.map((c) => (
                <button
                  key={c.key}
                  type="button"
                  onClick={() => clearChip(c)}
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 border border-hairline bg-mist hover:bg-hairline/40"
                >
                  {c.label}
                  <IconX className="w-3 h-3" aria-hidden="true" />
                  <span className="sr-only">Clear filter</span>
                </button>
              ))}
              <button
                type="button"
                onClick={clearAllFilters}
                className="text-xs text-terracotta uppercase tracking-wider2 hover:underline"
              >Clear all</button>
            </div>
          )}

          {dimPanelOpen && (
            <div id="dim-filter-panel" className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {DIMENSIONS.map((d) => (
                <div key={d.id} className="border border-hairline p-3 bg-mist/30">
                  <label className="block text-xs uppercase tracking-wider2 text-navy mb-2">{d.label}</label>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-muted">Min</span>
                    <input
                      type="number"
                      step="0.1" min="1" max="5"
                      value={dimMin[d.id] || ''}
                      onChange={(e) => {
                        const v = e.target.value;
                        setDimMin((p) => {
                          const n = { ...p };
                          if (v === '') delete n[d.id]; else n[d.id] = v;
                          return n;
                        });
                        setPage(1);
                      }}
                      className="form-input py-1 px-2 w-16 text-xs"
                      aria-label={`Minimum ${d.label}`}
                      placeholder="1.0"
                    />
                    <span className="text-muted">Max</span>
                    <input
                      type="number"
                      step="0.1" min="1" max="5"
                      value={dimMax[d.id] || ''}
                      onChange={(e) => {
                        const v = e.target.value;
                        setDimMax((p) => {
                          const n = { ...p };
                          if (v === '') delete n[d.id]; else n[d.id] = v;
                          return n;
                        });
                        setPage(1);
                      }}
                      className="form-input py-1 px-2 w-16 text-xs"
                      aria-label={`Maximum ${d.label}`}
                      placeholder="5.0"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Compare + Cohort toolbar (Phase 11A + 11C) */}
      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between bg-navy text-white px-4 py-2.5 mb-3 text-sm flex-wrap gap-y-2">
          <span>
            <strong>{selectedIds.size}</strong> selected
            {selectedIds.size === 1 && <span className="text-white/70 ml-2">· pick more for cohort or comparison</span>}
            {selectedIds.size > 2 && <span className="text-white/70 ml-2">· cohort view supports any N ≥ 2; compare needs exactly 2</span>}
          </span>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={clearSelection}
              className="text-xs uppercase tracking-wider2 text-white/80 hover:text-white"
            >Clear</button>
            <button
              type="button"
              onClick={onCompare}
              disabled={selectedIds.size !== 2}
              title={selectedIds.size !== 2 ? 'Compare requires exactly 2 sessions' : 'Side-by-side compare'}
              className={
                'inline-flex items-center gap-2 px-3 py-1.5 text-xs uppercase tracking-wider2 border ' +
                (selectedIds.size === 2
                  ? 'bg-gold border-gold text-navy hover:bg-gold-dark hover:text-white'
                  : 'border-white/30 text-white/40 cursor-not-allowed')
              }
            >
              <GitCompare className="w-3.5 h-3.5" /> Compare
            </button>
            <button
              type="button"
              onClick={onCohort}
              disabled={selectedIds.size < 2}
              title={selectedIds.size < 2 ? 'Cohort view requires at least 2 sessions' : 'Aggregate cohort view'}
              className={
                'inline-flex items-center gap-2 px-3 py-1.5 text-xs uppercase tracking-wider2 border ' +
                (selectedIds.size >= 2
                  ? 'bg-white text-navy border-white hover:bg-gold hover:border-gold'
                  : 'border-white/30 text-white/40 cursor-not-allowed')
              }
            >
              <Users className="w-3.5 h-3.5" /> Cohort
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="text-sm text-terracotta mb-4">{error}</div>
      )}

      <div className="bg-white border border-hairline overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">All sessions</caption>
          <thead>
            <tr className="text-[10px] uppercase tracking-wider2 text-muted border-b border-hairline">
              <th scope="col" className="text-left px-3 py-2.5 font-medium w-8">
                <span className="sr-only">Select for comparison</span>
              </th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Participant</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Organisation</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Stage</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Category</th>
              <th scope="col" className="text-left px-3 py-2.5 font-medium" title="Learning Agility">LA</th>
              <th scope="col" className="text-left px-3 py-2.5 font-medium" title="Tolerance for Ambiguity">TA</th>
              <th scope="col" className="text-left px-3 py-2.5 font-medium" title="Cognitive Flexibility">CF</th>
              <th scope="col" className="text-left px-3 py-2.5 font-medium" title="Self-Awareness Accuracy">SA</th>
              <th scope="col" className="text-left px-3 py-2.5 font-medium" title="AI Fluency">AI</th>
              <th scope="col" className="text-left px-3 py-2.5 font-medium" title="Systems Thinking">ST</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Completed</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Status</th>
              <th scope="col" className="px-4 py-2.5 font-medium w-8" />
            </tr>
          </thead>
          <tbody>
            {loading && Array.from({ length: 6 }).map((_, i) => (
              <tr key={i} className="border-b border-hairline">
                {Array.from({ length: 14 }).map((__, j) => (
                  <td key={j} className="px-4 py-3"><div className="h-3 bg-hairline/70 animate-pulse w-12" /></td>
                ))}
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={14} className="px-4 py-16 text-center">
                  <p className="text-muted italic">No sessions match these filters.</p>
                  <button
                    type="button"
                    onClick={clearAllFilters}
                    className="mt-3 inline-block text-sm text-navy hover:text-gold border-b border-transparent hover:border-gold"
                  >Clear filters</button>
                </td>
              </tr>
            )}
            {!loading && items.map((r) => {
              const dims = r.dimensions || {};
              const canCompare = isSessionCompleteForCompare(r);
              const isSelected = selectedIds.has(r.session_id);
              return (
                <tr key={r.session_id}
                    className={'border-b border-hairline hover:bg-mist transition-colors ' + (r.archived ? 'bg-mist/40' : '') + (isSelected ? ' bg-gold/10' : '')}>
                  <td className="px-3 py-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(r)}
                      disabled={!canCompare}
                      title={canCompare ? 'Select for comparison' : 'Comparison requires a completed session'}
                      aria-label={canCompare ? `Select ${r.participant?.name || r.session_id} for comparison` : 'Comparison requires a completed session'}
                      className="w-4 h-4 accent-navy disabled:opacity-30 disabled:cursor-not-allowed"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Link to={`/admin/sessions/${r.session_id}`}
                          className="text-navy font-medium hover:text-gold">
                      {r.redacted ? <span className="italic text-muted">(redacted)</span> : (r.participant?.name || '—')}
                    </Link>
                    {r.response_pattern_flag && (
                      <span className="ml-2 inline-block text-[9px] uppercase tracking-wider2 text-terracotta border border-terracotta/40 px-1.5 py-0.5"
                            title={`Response pattern flag: ${r.response_pattern_flag}`}>
                        flagged
                      </span>
                    )}
                    {r.redacted && (
                      <div className="text-[10px] uppercase tracking-wider2 text-terracotta mt-0.5">Soft-deleted</div>
                    )}
                    {r.participant?.email && !r.redacted && (
                      <div className="text-[11px] text-muted">{r.participant.email}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-ink/80">{r.participant?.organisation || '—'}</td>
                  <td className="px-4 py-3 text-ink/80 capitalize">{r.stage || '—'}</td>
                  <td className="px-4 py-3"><ScoreChip colour={r.overall_colour} size="sm">{r.overall_category || 'n/a'}</ScoreChip></td>
                  <td className="px-3 py-3 tabular-nums text-ink/80">{fmtScore(dims.learning_agility)}</td>
                  <td className="px-3 py-3 tabular-nums text-ink/80">{fmtScore(dims.tolerance_for_ambiguity)}</td>
                  <td className="px-3 py-3 tabular-nums text-ink/80">{fmtScore(dims.cognitive_flexibility)}</td>
                  <td className="px-3 py-3 tabular-nums text-ink/80">{fmtScore(dims.self_awareness_accuracy)}</td>
                  <td className="px-3 py-3 tabular-nums text-ink/80">{fmtScore(dims.ai_fluency)}</td>
                  <td className="px-3 py-3 tabular-nums text-ink/80">{fmtScore(dims.systems_thinking)}</td>
                  <td className="px-4 py-3 text-ink/80">{fmtDate(r.completed_at)}</td>
                  <td className="px-4 py-3 text-ink/80">
                    {r.archived ? <span className="inline-flex items-center gap-1 text-xs text-gold-dark"><Lock className="w-3 h-3" />Archived</span> : r.status}
                  </td>
                  <td className="px-2 py-3 relative text-right">
                    <button type="button" className="p-1 hover:bg-hairline" onClick={() => setMenuOpenFor(menuOpenFor === r.session_id ? null : r.session_id)} aria-label="Row actions">
                      <MoreHorizontal className="w-4 h-4" />
                    </button>
                    {menuOpenFor === r.session_id && (
                      <div className="absolute right-0 top-10 z-10 w-52 bg-white border border-hairline shadow-lg text-left text-sm"
                           onMouseLeave={() => setMenuOpenFor(null)}>
                        <Link to={`/admin/sessions/${r.session_id}`} className="block px-4 py-2 hover:bg-mist">View detail</Link>
                        <button type="button" disabled={actionPending === r.session_id}
                                onClick={() => onArchiveToggle(r)}
                                className="w-full text-left px-4 py-2 hover:bg-mist flex items-center gap-2">
                          {r.archived ? <ArchiveRestore className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
                          {r.archived ? 'Unarchive' : 'Archive'}
                        </button>
                        {!r.deleted_at && (
                          <button type="button" disabled={actionPending === r.session_id}
                                  onClick={() => onSoftDelete(r)}
                                  className="w-full text-left px-4 py-2 hover:bg-mist text-terracotta flex items-center gap-2">
                            <Trash2 className="w-3.5 h-3.5" /> Soft delete
                          </button>
                        )}
                        {r.deleted_at && (
                          <button type="button" disabled={actionPending === r.session_id}
                                  onClick={() => onRestore(r)}
                                  className="w-full text-left px-4 py-2 hover:bg-mist flex items-center gap-2">
                            <RotateCcw className="w-3.5 h-3.5" /> Restore
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="mt-5 flex items-center justify-between text-sm">
        <p className="text-muted">
          Showing {items.length > 0 ? ((page - 1) * pageSize + 1) : 0}–{((page - 1) * pageSize) + items.length} of {total}
        </p>
        <div className="flex items-center gap-3">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="btn-ghost disabled:opacity-40 py-2 px-3">
            <ChevronLeft className="w-4 h-4" /> Prev
          </button>
          <span className="text-ink/70">Page {page} of {totalPages}</span>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="btn-ghost disabled:opacity-40 py-2 px-3">
            Next <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </section>
  );
}
