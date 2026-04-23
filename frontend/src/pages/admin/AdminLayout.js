import React, { useEffect } from 'react';
import { Navigate, Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { LogOut, Settings, ListChecks } from 'lucide-react';
import { useAdmin } from '../../store/adminStore';

export default function AdminLayout() {
  const { email, checked, refresh, logout } = useAdmin();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (!checked) refresh();
  }, [checked, refresh]);

  if (!checked) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <p className="text-sm uppercase tracking-wider2 text-muted">Loading admin…</p>
      </div>
    );
  }

  if (!email) {
    // Redirect to login, preserving intent
    return <Navigate to={`/admin/login?next=${encodeURIComponent(pathname)}`} replace />;
  }

  async function onLogout() {
    await logout();
    navigate('/admin/login', { replace: true });
  }

  const navItems = [
    { to: '/admin/settings', label: 'Settings', icon: Settings },
    { to: '#', label: 'Sessions', icon: ListChecks, disabled: true, hint: 'Phase 8' },
  ];

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-hairline">
        <div className="max-w-content mx-auto px-6 sm:px-8 h-16 flex items-center justify-between">
          <Link to="/admin" className="flex items-center gap-3">
            <span className="h-6 w-[2px] bg-gold" aria-hidden="true" />
            <span className="font-serif text-navy text-lg tracking-wide">Admin Console</span>
          </Link>
          <div className="flex items-center gap-5 text-sm">
            <span className="text-muted hidden sm:inline">{email}</span>
            <button
              type="button"
              onClick={onLogout}
              className="inline-flex items-center gap-2 text-xs uppercase tracking-wider2 text-navy hover:text-navy-dark font-medium border-b border-transparent hover:border-gold transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" strokeWidth={2} /> Log out
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-content mx-auto px-6 sm:px-8 pt-10 pb-20 flex gap-10">
        <aside className="w-48 shrink-0 hidden md:block">
          <nav>
            <ul className="space-y-1">
              {navItems.map((it) => {
                const Icon = it.icon;
                const active = pathname === it.to || pathname.startsWith(it.to + '/');
                if (it.disabled) {
                  return (
                    <li key={it.label} className="flex items-center gap-2 text-xs uppercase tracking-wider2 text-muted px-3 py-2 cursor-not-allowed">
                      <Icon className="w-3.5 h-3.5" />
                      {it.label}
                      <span className="text-[10px] normal-case text-gold ml-1">({it.hint})</span>
                    </li>
                  );
                }
                return (
                  <li key={it.label}>
                    <Link
                      to={it.to}
                      className={
                        'flex items-center gap-2 text-xs uppercase tracking-wider2 px-3 py-2 border-l-2 transition-colors ' +
                        (active
                          ? 'border-gold text-navy font-semibold bg-mist'
                          : 'border-transparent text-navy hover:border-gold hover:bg-mist/60')
                      }
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {it.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>

        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>

      <footer className="border-t border-hairline">
        <div className="max-w-content mx-auto px-6 sm:px-8 py-5 text-xs uppercase tracking-wider2 text-muted">
          Admin console
        </div>
      </footer>
    </div>
  );
}
