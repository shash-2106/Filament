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
  BookOpen,
} from 'lucide-react';
import { useHealthQuery } from '../../api/queries';
import { useAuth } from '../../context/auth';
import { FilamentLogo } from '../brand/FilamentLogo';

interface NavItem {
  to: string;
  label: string;
  icon: React.ElementType;
  badge?: string;
}

const navItems: NavItem[] = [
  { to: '/', label: 'Overview', icon: Compass },
  { to: '/guide', label: 'Interactive Guide', icon: BookOpen, badge: 'Tour' },
  { to: '/memory', label: 'Memories', icon: Database },
  { to: '/evidence', label: 'Supporting Evidence', icon: ShieldCheck },
  { to: '/dependencies', label: 'Memory Connections', icon: GitFork },
  { to: '/agents', label: 'Connected AI Agents', icon: Bot },
  { to: '/integrations', label: 'Integrations', icon: Layers },
  { to: '/activity', label: 'Activity History', icon: Activity },
];

export const Navigation: React.FC = () => {
  const { isSuccess, isError } = useHealthQuery();
  const { apiKey } = useAuth();

  return (
    <aside className="w-60 bg-[#0E1714] text-graphite-text border-r border-[#294537] flex flex-col flex-shrink-0 h-screen select-none relative z-40">
      {/* Brand & Technical Instrument Header */}
      <div className="p-4 border-b border-[#294537]">
        <NavLink to="/welcome" className="flex items-center gap-2.5 group">
          <FilamentLogo size="md" animated={true} />
          <div>
            <h1 className="font-heading text-base font-semibold tracking-wider text-graphite-text leading-none group-hover:text-phosphor transition-colors">
              FILAMENT
            </h1>
            <p className="text-[10px] font-mono tracking-widest text-graphite-text-tertiary uppercase mt-1">
              Governed Agent Memory
            </p>
          </div>
        </NavLink>
      </div>

      {/* Navigation Sections */}
      <nav className="flex-1 px-2.5 py-4 space-y-0.5 overflow-y-auto">
        <div className="px-2.5 pb-2 text-[10px] font-mono font-medium tracking-widest text-graphite-text-tertiary uppercase">
          Workstation
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center justify-between px-2.5 py-2 rounded text-xs font-sans transition-all group ${
                  isActive
                    ? 'bg-[#1C3027] text-phosphor font-medium border border-phosphor-border shadow-xs'
                    : 'text-graphite-text-secondary hover:bg-[#14231D] hover:text-graphite-text border border-transparent'
                }`
              }
            >
              <div className="flex items-center gap-2.5">
                <Icon className="w-4 h-4 flex-shrink-0 text-inherit transition-transform group-hover:scale-105" />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#14231D] text-phosphor border border-[#294537]">
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Telemetry Footer Status */}
      <div className="p-3.5 border-t border-[#294537] bg-[#0B1210] space-y-2.5 text-xs font-mono">
        {/* Gateway connection indicator */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-graphite-text-tertiary">
            <Server className="w-3.5 h-3.5 text-phosphor" />
            <span>Gateway API</span>
          </div>
          {isSuccess && (
            <span className="inline-flex items-center gap-1 text-[11px] text-phosphor font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-phosphor animate-pulse" />
              healthy
            </span>
          )}
          {isError && (
            <span className="inline-flex items-center gap-1 text-[11px] text-[#A96580]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#A96580]" />
              offline
            </span>
          )}
          {!isSuccess && !isError && (
            <span className="inline-flex items-center gap-1 text-[11px] text-graphite-text-tertiary">
              <span className="w-1.5 h-1.5 rounded-full bg-graphite-text-tertiary animate-pulse" />
              connecting
            </span>
          )}
        </div>

        {/* Auth status indicator */}
        <div className="flex items-center justify-between pt-1 border-t border-[#1C3027]">
          <div className="flex items-center gap-1.5 text-graphite-text-tertiary">
            <Key className="w-3.5 h-3.5 text-phosphor-secondary" />
            <span>Agent Key</span>
          </div>
          <span
            className={`text-[11px] ${
              apiKey ? 'text-phosphor font-medium' : 'text-[#E5B45E]'
            }`}
          >
            {apiKey ? 'AUTHENTICATED' : 'ANONYMOUS'}
          </span>
        </div>
      </div>
    </aside>
  );
};
