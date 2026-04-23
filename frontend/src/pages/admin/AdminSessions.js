import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ChevronLeft, ChevronRight, Lock, Archive, ArchiveRestore, Trash2, RotateCcw, MoreHorizontal } from 'lucide-react';
import {
  listSessions, patchSession, softDeleteSession, restoreSession, apiErrorMessage,
} from '../../lib/adminApi';
import ScoreChip from '../../components/admin/ScoreChip';

const STATUS_OPTIONS = ['active', 'completed', 'failed', 'abandoned'];

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

export default function AdminSessions() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState([]);
  const [archivedFilter, setArchivedFilter] = useState('');   // '' | 'only' | 'exclude'
  const [includeDeleted, setIncludeDeleted] = useState(true);
  const [sort, setSort] = useState('-created_at');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionPending, setActionPending] = useState(null);
  const [menuOpenFor, setMenuOpenFor] = useState(null);
  const debounceRef = useRef(null);

  const load = useCallback(async () => {
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
      const data = await listSessions(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(apiErrorMessage(e, 'Could not load sessions.'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, sort, q, statusFilter, archivedFilter, includeDeleted]);

  // Debounce search — re-load 300 ms after typing stops
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
            />
          </div>
          <select
            value={sort}
            onChange={(e) => { setSort(e.target.value); setPage(1); }}
            className="form-input py-2.5 text-sm max-w-[210px]"
          >
            <option value="-created_at">Newest first</option>
            <option value="created_at">Oldest first</option>
            <option value="-completed_at">Recently completed</option>
            <option value="participant.name">Name A–Z</option>
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
      </div>

      {error && (
        <div className="text-sm text-terracotta mb-4">{error}</div>
      )}

      <div className="bg-white border border-hairline overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">All sessions</caption>
          <thead>
            <tr className="text-[10px] uppercase tracking-wider2 text-muted border-b border-hairline">
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Participant</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Organisation</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Stage</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Category</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Started</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Completed</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Duration</th>
              <th scope="col" className="text-left px-4 py-2.5 font-medium">Status</th>
              <th scope="col" className="px-4 py-2.5 font-medium w-8" />
            </tr>
          </thead>
          <tbody>
            {loading && Array.from({ length: 6 }).map((_, i) => (
              <tr key={i} className="border-b border-hairline">
                {Array.from({ length: 9 }).map((__, j) => (
                  <td key={j} className="px-4 py-3"><div className="h-3 bg-hairline/70 animate-pulse w-16" /></td>
                ))}
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-16 text-center">
                  <p className="text-muted italic">No sessions match your filters.</p>
                  <Link to="/" className="mt-3 inline-block text-sm text-navy hover:text-gold border-b border-transparent hover:border-gold">Start a demo session →</Link>
                </td>
              </tr>
            )}
            {!loading && items.map((r) => (
              <tr key={r.session_id}
                  className={'border-b border-hairline hover:bg-mist transition-colors ' + (r.archived ? 'bg-mist/40' : '')}>
                <td className="px-4 py-3">
                  <Link to={`/admin/sessions/${r.session_id}`}
                        className="text-navy font-medium hover:text-gold">
                    {r.redacted ? <span className="italic text-muted">(redacted)</span> : (r.participant?.name || '—')}
                  </Link>
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
                <td className="px-4 py-3 text-ink/80">{fmtDate(r.created_at)}</td>
                <td className="px-4 py-3 text-ink/80">{fmtDate(r.completed_at)}</td>
                <td className="px-4 py-3 text-ink/80">{fmtDuration(r.duration_seconds)}</td>
                <td className="px-4 py-3 text-ink/80">
                  {r.archived ? <span className="inline-flex items-center gap-1 text-xs text-gold-dark"><Lock className="w-3 h-3" />Archived</span> : r.status}
                </td>
                <td className="px-2 py-3 relative text-right">
                  <button type="button" className="p-1 hover:bg-hairline" onClick={() => setMenuOpenFor(menuOpenFor === r.session_id ? null : r.session_id)}>
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
            ))}
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
