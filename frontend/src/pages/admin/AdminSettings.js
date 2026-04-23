import React, { useEffect, useState } from 'react';
import { Check, X, Loader2, Eye, EyeOff, RefreshCcw } from 'lucide-react';
import { getSettings, putSettings, testSlot, testFallback, adminErrorMessage } from '../../lib/adminApi';

function modelsFor(catalog, provider) {
  if (!provider || !catalog || !catalog.providers) return [];
  const p = catalog.providers[provider];
  return p ? p.models : [];
}

function pillClasses(ok) {
  if (ok === true) return 'bg-green-50 text-green-800 border-green-200';
  if (ok === false) return 'bg-red-50 text-red-800 border-red-200';
  return 'bg-mist text-muted border-hairline';
}

function SlotCard({ title, slotKey, state, setState, catalog, testResult, onTest, onSave, onClear, saving, testing }) {
  const [showKey, setShowKey] = useState(false);
  const providerModels = modelsFor(catalog, state.provider);

  function change(key, value) {
    setState((s) => ({ ...s, [key]: value }));
  }

  return (
    <div className="card card-gold-top">
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif text-xl text-navy">{title}</h2>
        {state.has_key && !state.api_key && (
          <span className="text-xs uppercase tracking-wider2 text-muted">
            Saved: <span className="font-mono text-navy">{state.key_hint || '••••'}</span>
          </span>
        )}
      </div>

      <div className="mt-6 space-y-5">
        <label className="block">
          <span className="text-xs uppercase tracking-wider2 text-navy font-medium">Provider</span>
          <select
            className="form-input mt-2"
            value={state.provider || ''}
            onChange={(e) => {
              const p = e.target.value;
              // Reset model if the current one is not valid for the new provider
              setState((s) => ({
                ...s,
                provider: p,
                model: modelsFor(catalog, p).some((m) => m.id === s.model) ? s.model : '',
              }));
            }}
          >
            <option value="">— Select provider —</option>
            {catalog && catalog.providers && Object.entries(catalog.providers).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-xs uppercase tracking-wider2 text-navy font-medium">Model</span>
          <select
            className="form-input mt-2"
            value={state.model || ''}
            onChange={(e) => change('model', e.target.value)}
            disabled={!state.provider}
          >
            <option value="">— Select model —</option>
            {providerModels.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-xs uppercase tracking-wider2 text-navy font-medium">Label (optional)</span>
          <input
            className="form-input mt-2"
            value={state.label || ''}
            onChange={(e) => change('label', e.target.value)}
            placeholder="e.g. Production Anthropic account"
          />
        </label>

        <div>
          <span className="text-xs uppercase tracking-wider2 text-navy font-medium">API key</span>
          <div className="mt-2 relative">
            <input
              type={showKey ? 'text' : 'password'}
              autoComplete="off"
              className="form-input pr-20 font-mono"
              placeholder={state.has_key ? 'Enter to replace — leave blank to keep saved' : 'Paste key…'}
              value={state.api_key || ''}
              onChange={(e) => change('api_key', e.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowKey((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-xs uppercase tracking-wider2 text-navy hover:text-navy-dark inline-flex items-center gap-1 px-2"
            >
              {showKey ? <><EyeOff className="w-3.5 h-3.5" />Hide</> : <><Eye className="w-3.5 h-3.5" />Reveal</>}
            </button>
          </div>
        </div>

        {testResult && (
          <div className={'inline-flex items-center gap-2 border px-3 py-1 text-xs ' + pillClasses(testResult.ok)}>
            {testResult.ok === true && <Check className="w-3.5 h-3.5" strokeWidth={2.5} />}
            {testResult.ok === false && <X className="w-3.5 h-3.5" strokeWidth={2.5} />}
            {testResult.message}
          </div>
        )}

        <div className="flex items-center gap-3 flex-wrap pt-1">
          <button type="button" onClick={onSave} disabled={saving} className="btn-primary disabled:opacity-60">
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" onClick={onTest} disabled={testing} className="btn-secondary disabled:opacity-60">
            {testing ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Testing…</>
            ) : (
              <><RefreshCcw className="w-4 h-4" /> Test connection</>
            )}
          </button>
          {state.has_key && (
            <button type="button" onClick={onClear} className="btn-ghost">
              Clear key
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AdminSettings() {
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);
  const [primary, setPrimary] = useState({});
  const [secondary, setSecondary] = useState({});
  const [fallbackModel, setFallbackModel] = useState('claude-opus-4-6');
  const [fallbackModels, setFallbackModels] = useState([]);
  const [loadErr, setLoadErr] = useState(null);

  const [saving, setSaving] = useState({ primary: false, secondary: false, fallback: false });
  const [testing, setTesting] = useState({ primary: false, secondary: false, fallback: false });
  const [testResult, setTestResult] = useState({ primary: null, secondary: null, fallback: null });
  const [updatedAt, setUpdatedAt] = useState(null);
  const [updatedBy, setUpdatedBy] = useState(null);

  async function load() {
    setLoading(true);
    setLoadErr(null);
    try {
      const s = await getSettings();
      setCatalog(s.catalog);
      setFallbackModels(s.catalog?.fallback_models || []);
      setPrimary({ ...(s.primary || {}), api_key: '' });
      setSecondary({ ...(s.secondary || {}), api_key: '' });
      setFallbackModel(s.fallback_model || 'claude-opus-4-6');
      setUpdatedAt(s.updated_at);
      setUpdatedBy(s.updated_by);
    } catch (e) {
      setLoadErr(adminErrorMessage(e, 'Could not load settings.'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function save(slotKey) {
    const state = slotKey === 'primary' ? primary : secondary;
    const body = {};
    const slotBody = {
      provider: state.provider || null,
      model: state.model || null,
      label: state.label || null,
    };
    if (state.api_key !== undefined) {
      slotBody.api_key = state.api_key;  // '' clears, set value saves
    }
    body[slotKey] = slotBody;
    setSaving((s) => ({ ...s, [slotKey]: true }));
    setTestResult((r) => ({ ...r, [slotKey]: null }));
    try {
      const res = await putSettings(body);
      const fresh = slotKey === 'primary' ? res.primary : res.secondary;
      if (slotKey === 'primary') setPrimary({ ...(fresh || {}), api_key: '' });
      else setSecondary({ ...(fresh || {}), api_key: '' });
      setUpdatedAt(res.updated_at); setUpdatedBy(res.updated_by);
    } catch (e) {
      setTestResult((r) => ({ ...r, [slotKey]: { ok: false, message: adminErrorMessage(e, 'Save failed.') } }));
    } finally {
      setSaving((s) => ({ ...s, [slotKey]: false }));
    }
  }

  async function clear(slotKey) {
    setSaving((s) => ({ ...s, [slotKey]: true }));
    try {
      const body = {}; body[slotKey] = { api_key: '' };
      const res = await putSettings(body);
      const fresh = slotKey === 'primary' ? res.primary : res.secondary;
      if (slotKey === 'primary') setPrimary({ ...(fresh || {}), api_key: '' });
      else setSecondary({ ...(fresh || {}), api_key: '' });
      setTestResult((r) => ({ ...r, [slotKey]: { ok: true, message: 'Key cleared.' } }));
    } catch (e) {
      setTestResult((r) => ({ ...r, [slotKey]: { ok: false, message: adminErrorMessage(e, 'Clear failed.') } }));
    } finally {
      setSaving((s) => ({ ...s, [slotKey]: false }));
    }
  }

  async function runTest(slotKey) {
    const state = slotKey === 'primary' ? primary : secondary;
    if (!state.provider || !state.model) {
      setTestResult((r) => ({ ...r, [slotKey]: { ok: false, message: 'Select provider and model first.' } }));
      return;
    }
    setTesting((t) => ({ ...t, [slotKey]: true }));
    setTestResult((r) => ({ ...r, [slotKey]: null }));
    try {
      const data = await testSlot(slotKey, state.provider, state.model, state.api_key || undefined);
      if (data.ok) {
        setTestResult((r) => ({ ...r, [slotKey]: { ok: true, message: `OK — ${data.latency_ms}ms — ${data.model}` } }));
      } else {
        setTestResult((r) => ({ ...r, [slotKey]: { ok: false, message: `${data.error_category || 'error'}: ${data.error || 'failed'}` } }));
      }
    } catch (e) {
      setTestResult((r) => ({ ...r, [slotKey]: { ok: false, message: adminErrorMessage(e, 'Test failed.') } }));
    } finally {
      setTesting((t) => ({ ...t, [slotKey]: false }));
    }
  }

  async function runFallbackTest() {
    setTesting((t) => ({ ...t, fallback: true }));
    setTestResult((r) => ({ ...r, fallback: null }));
    try {
      const data = await testFallback();
      if (data.ok) {
        setTestResult((r) => ({ ...r, fallback: { ok: true, message: `OK — ${data.latency_ms}ms — ${data.model}` } }));
      } else {
        setTestResult((r) => ({ ...r, fallback: { ok: false, message: `${data.error_category || 'error'}: ${data.error || 'failed'}` } }));
      }
    } catch (e) {
      setTestResult((r) => ({ ...r, fallback: { ok: false, message: adminErrorMessage(e, 'Test failed.') } }));
    } finally {
      setTesting((t) => ({ ...t, fallback: false }));
    }
  }

  async function saveFallback(value) {
    setSaving((s) => ({ ...s, fallback: true }));
    try {
      const res = await putSettings({ fallback_model: value });
      setFallbackModel(res.fallback_model);
      setUpdatedAt(res.updated_at); setUpdatedBy(res.updated_by);
    } catch (e) {
      setTestResult((r) => ({ ...r, fallback: { ok: false, message: adminErrorMessage(e, 'Save failed.') } }));
    } finally {
      setSaving((s) => ({ ...s, fallback: false }));
    }
  }

  if (loading) {
    return <p className="text-sm uppercase tracking-wider2 text-muted">Loading settings…</p>;
  }
  if (loadErr) {
    return <p className="text-sm text-red-700">{loadErr}</p>;
  }

  return (
    <section>
      <span className="eyebrow">Settings</span>
      <h1 className="mt-4 text-3xl font-serif text-navy tracking-tight">LLM Providers &amp; Keys</h1>
      <span className="mt-5 gold-rule block" aria-hidden="true" />
      <p className="mt-6 text-ink/75 leading-relaxed max-w-2xl">
        Configure the models used for the AI Fluency discussion and synthesis output. The
        Emergent-key fallback is always available as a third-tier safety net.
      </p>
      {updatedAt && (
        <p className="mt-3 text-xs uppercase tracking-wider2 text-muted">
          Last updated {new Date(updatedAt).toLocaleString()} by {updatedBy || 'system'}
        </p>
      )}

      <div className="mt-10 grid gap-8 lg:grid-cols-2">
        <SlotCard
          title="Primary provider"
          slotKey="primary"
          state={primary}
          setState={setPrimary}
          catalog={catalog}
          testResult={testResult.primary}
          onTest={() => runTest('primary')}
          onSave={() => save('primary')}
          onClear={() => clear('primary')}
          saving={saving.primary}
          testing={testing.primary}
        />
        <SlotCard
          title="Secondary provider (fallback #2)"
          slotKey="secondary"
          state={secondary}
          setState={setSecondary}
          catalog={catalog}
          testResult={testResult.secondary}
          onTest={() => runTest('secondary')}
          onSave={() => save('secondary')}
          onClear={() => clear('secondary')}
          saving={saving.secondary}
          testing={testing.secondary}
        />
      </div>

      <div className="mt-12 card card-gold-top">
        <div className="flex items-baseline justify-between flex-wrap gap-3">
          <div>
            <h2 className="font-serif text-xl text-navy">Built-in fallback</h2>
            <p className="mt-2 text-xs uppercase tracking-wider2 text-muted">Emergent LLM key — built in</p>
          </div>
        </div>
        <div className="mt-6 grid sm:grid-cols-2 gap-5">
          <label className="block">
            <span className="text-xs uppercase tracking-wider2 text-navy font-medium">Fallback model</span>
            <select
              className="form-input mt-2"
              value={fallbackModel}
              onChange={(e) => saveFallback(e.target.value)}
            >
              {fallbackModels.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-6 flex items-center gap-3">
          <button type="button" onClick={runFallbackTest} disabled={testing.fallback} className="btn-secondary disabled:opacity-60">
            {testing.fallback ? 'Testing…' : 'Test fallback'}
          </button>
          {testResult.fallback && (
            <div className={'inline-flex items-center gap-2 border px-3 py-1 text-xs ' + pillClasses(testResult.fallback.ok)}>
              {testResult.fallback.ok === true && <Check className="w-3.5 h-3.5" strokeWidth={2.5} />}
              {testResult.fallback.ok === false && <X className="w-3.5 h-3.5" strokeWidth={2.5} />}
              {testResult.fallback.message}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
