import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Search, Key, ChevronDown, Shield, BookOpen } from 'lucide-react';
import { useAuth } from '../../context/auth';
import { Button } from '../common/Button';

export const Header: React.FC = () => {
  const { workspaceName, workspaceSlug, apiKey, setApiKey } = useAuth();
  const [isKeyModalOpen, setIsKeyModalOpen] = useState(false);
  const [inputKey, setInputKey] = useState(apiKey);

  const handleSaveKey = (e: React.FormEvent) => {
    e.preventDefault();
    setApiKey(inputKey);
    setIsKeyModalOpen(false);
  };

  return (
    <>
      <header className="h-14 bg-[#0E1714]/90 backdrop-blur-md border-b border-[#294537] px-6 flex items-center justify-between gap-4 select-none flex-shrink-0 z-30 sticky top-0">
        {/* Workspace Context Selector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-[#14231D] border border-[#294537] hover:border-phosphor/60 cursor-pointer transition-colors group shadow-xs">
            <span className="w-2 h-2 rounded-full bg-phosphor animate-pulse"></span>
            <span className="font-heading text-sm text-graphite-text font-medium leading-none">
              {workspaceName}
            </span>
            <span className="text-[11px] font-mono text-graphite-text-tertiary">
              ({workspaceSlug})
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-graphite-text-tertiary group-hover:text-phosphor transition-colors" />
          </div>

          <div className="hidden md:flex items-center gap-1.5 text-xs font-mono text-graphite-text-tertiary border-l border-[#294537] pl-3">
            <span>repo:</span>
            <span className="font-medium text-graphite-text">filament/core</span>
            <span className="text-[10px] text-graphite-text-tertiary font-mono">(default)</span>
          </div>
        </div>

        {/* Search Entry Point */}
        <div className="flex-1 max-w-md mx-4">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-graphite-text-tertiary" />
            <input
              type="text"
              placeholder="Search memories, evidence hashes, connections (Press /)"
              className="w-full bg-[#14231D] border border-[#294537] rounded py-1.5 pl-8 pr-3 text-xs font-sans text-graphite-text placeholder:text-graphite-text-tertiary focus:outline-none focus:border-phosphor focus:ring-1 focus:ring-phosphor/30 transition-all shadow-xs"
            />
          </div>
        </div>

        {/* Guide and Agent Auth Actions */}
        <div className="flex items-center gap-2.5">
          <NavLink
            to="/guide"
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-1 text-xs font-medium rounded border transition-all cursor-pointer shadow-xs ${
                isActive
                  ? 'bg-phosphor text-[#0B1210] border-phosphor font-semibold'
                  : 'bg-[#14231D] border-[#294537] hover:border-phosphor/60 text-graphite-text'
              }`
            }
            title="Open Interactive Guide & Walkthrough"
          >
            <BookOpen className="w-3.5 h-3.5 text-inherit" />
            <span>Guide & Tour</span>
          </NavLink>

          <button
            onClick={() => {
              setInputKey(apiKey);
              setIsKeyModalOpen(true);
            }}
            className="flex items-center gap-2 px-2.5 py-1 text-xs font-mono rounded border border-[#294537] bg-[#14231D] hover:border-phosphor/60 text-graphite-text transition-colors cursor-pointer shadow-xs"
            title="Configure Agent API Key for authenticated requests"
          >
            <Key className="w-3.5 h-3.5 text-phosphor" />
            <span>{apiKey ? 'Agent Key Set' : 'Configure API Key'}</span>
            <span className={`w-1.5 h-1.5 rounded-full ${apiKey ? 'bg-phosphor' : 'bg-[#E5B45E]'}`} />
          </button>
        </div>
      </header>

      {/* API Key Modal */}
      {isKeyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <div className="bg-[#14231D] border border-[#294537] rounded-md max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-phosphor" />
              <h3 className="font-heading text-base font-semibold text-graphite-text">
                Agent Authentication
              </h3>
            </div>
            <p className="text-xs text-graphite-text-secondary leading-relaxed">
              Requests to create claims or evaluate environment conditions require an Agent Bearer API Key.
            </p>

            <form onSubmit={handleSaveKey} className="space-y-3">
              <div>
                <label className="block text-[11px] font-mono text-graphite-text-tertiary mb-1 uppercase tracking-wider">
                  API Key
                </label>
                <input
                  type="password"
                  value={inputKey}
                  onChange={(e) => setInputKey(e.target.value)}
                  placeholder="fil_live_..."
                  className="w-full bg-[#0B1210] border border-[#294537] rounded px-3 py-1.5 text-xs font-mono text-graphite-text focus:outline-none focus:border-phosphor"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsKeyModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="sm">
                  Save Credentials
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
