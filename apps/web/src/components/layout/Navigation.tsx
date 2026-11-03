import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Compass,
  Database,
  ShieldCheck,
  GitFork,
  Bot,
  Layers,
  Activity,
  Server,
  Key,
} from 'lucide-react';
import { useHealthQuery } from '../../api/queries';
import { useAuth } from '../../context/auth';

interface NavItem {
  to: string;
  label: string;
  icon: React.ElementType;
  badge?: string;
}

const navItems: NavItem[] = [
  { to: '/', label: 'Overview', icon: Compass },
  { to: '/memory', label: 'Memory', icon: Database },
  { to: '/evidence', label: 'Evidence', icon: ShieldCheck },
  { to: '/dependencies', label: 'Dependencies', icon: GitFork },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/integrations', label: 'Integrations', icon: Layers },
  { to: '/activity', label: 'Activity', icon: Activity },
];

export const Navigation: React.FC = () => {
  const { data: health, isSuccess, isError } = useHealthQuery();
  const { apiKey } = useAuth();

  return (
    <aside className="w-64 bg-aubergine-deep text-parchment-light border-r border-aubergine-border flex flex-col flex-shrink-0 h-screen select-none">
      {/* Brand & Editorial Instrument Masthead */}
      <div className="p-5 border-b border-aubergine-border/80">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-sm bg-copper flex items-center justify-center text-parchment-light font-editorial font-bold text-base shadow-sm">
            F
          </div>
          <div>
            <h1 className="font-editorial text-xl font-medium tracking-wide text-parchment-light leading-none">
              FILAMENT
            </h1>
            <p className="text-[11px] font-mono tracking-wider text-aubergine-text-muted uppercase mt-1">
              Governed Agent Memory
            </p>
          </div>
        </div>
      </div>

      {/* Navigation Sections */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[10px] font-mono font-medium tracking-widest text-aubergine-text-muted uppercase">
          Workstation
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center justify-between px-3 py-2 text-sm font-sans rounded-sm transition-all group ${
                  isActive
                    ? 'bg-copper text-parchment-light font-medium shadow-xs'
                    : 'text-parchment-light/80 hover:bg-aubergine-surface hover:text-parchment-light'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className="flex items-center gap-2.5">
                    <Icon
                      className={`w-4 h-4 transition-colors ${
                        isActive ? 'text-parchment-light' : 'text-aubergine-text-muted group-hover:text-copper-light'
                      }`}
                    />
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded-sm ${
                        isActive
                          ? 'bg-parchment/20 text-parchment-light'
                          : 'bg-aubergine-surface text-stone border border-aubergine-border'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Technical Footer & Connection Telemetry */}
      <div className="p-3.5 border-t border-aubergine-border bg-aubergine text-xs font-mono space-y-2">
        <div className="flex items-center justify-between text-aubergine-text-muted">
          <span className="flex items-center gap-1.5">
            <Server className="w-3.5 h-3.5" />
            <span>Gateway API</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                isSuccess ? 'bg-sage' : isError ? 'bg-terracotta' : 'bg-citron animate-pulse'
              }`}
            />
            <span className="text-[11px] text-parchment-light/90">
              {isSuccess ? health?.status || 'connected' : isError ? 'offline' : 'connecting'}
            </span>
          </span>
        </div>

        <div className="flex items-center justify-between pt-1 text-[11px] text-aubergine-text-muted border-t border-aubergine-border/60">
          <span className="flex items-center gap-1">
            <Key className="w-3 h-3 text-copper-light" />
            <span>Auth</span>
          </span>
          <span className="text-parchment-light/80">
            {apiKey ? `${apiKey.slice(0, 7)}...` : 'No key set'}
          </span>
        </div>
      </div>
    </aside>
  );
};

