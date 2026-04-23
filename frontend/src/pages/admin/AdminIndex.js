import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Settings } from 'lucide-react';

export default function AdminIndex() {
  return (
    <section>
      <span className="eyebrow">Overview</span>
      <h1 className="mt-4 text-3xl font-serif text-navy tracking-tight">Admin Console</h1>
      <span className="mt-5 gold-rule block" aria-hidden="true" />
      <p className="mt-6 text-ink/75 leading-relaxed max-w-2xl">
        Configure the AI models that power the assessment and review completed sessions.
      </p>
      <div className="mt-10 grid gap-6 sm:grid-cols-2 max-w-3xl">
        <Link
          to="/admin/settings"
          className="card card-gold-top hover:shadow-sm transition-shadow"
        >
          <div className="flex items-center gap-2 text-navy">
            <Settings className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider2 font-medium">Settings</span>
          </div>
          <h2 className="mt-3 text-xl font-serif text-navy">LLM providers &amp; keys</h2>
          <p className="mt-3 text-sm text-ink/70 leading-relaxed">
            Choose primary and secondary providers, paste API keys, and test connections. The Emergent fallback is always on.
          </p>
          <p className="mt-5 inline-flex items-center gap-2 text-xs uppercase tracking-wider2 text-gold font-medium">
            Open
            <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
          </p>
        </Link>

        <div className="card border-dashed text-muted">
          <p className="text-xs uppercase tracking-wider2 text-gold font-medium">Phase 8</p>
          <h2 className="mt-3 text-xl font-serif text-navy">Sessions</h2>
          <p className="mt-3 text-sm text-ink/70 leading-relaxed">
            Session list, search, review, export and archive come online in a later phase.
          </p>
        </div>
      </div>
    </section>
  );
}
