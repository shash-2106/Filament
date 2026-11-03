import React, { useState } from 'react';
import { Search, Key, ChevronDown, Shield } from 'lucide-react';
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
      <header className="h-14 bg-parchment-light border-b border-stone-border px-6 flex items-center justify-between gap-4 select-none flex-shrink-0">
        {/* Workspace Context Selector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-sm bg-parchment border border-stone-border hover:border-copper/70 cursor-pointer transition-colors group">
            <span className="w-2 h-2 rounded-full bg-copper"></span>
            <span className="font-editorial text-base text-aubergine font-medium leading-none">
              {workspaceName}
            </span>
            <span className="text-[11px] font-mono text-stone-muted">
              ({workspaceSlug})
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-stone-muted group-hover:text-copper transition-colors" />
          </div>

          <div className="hidden md:flex items-center gap-1.5 text-xs font-mono text-stone-muted border-l border-stone-border pl-3">
            <span className="text-aubergine/60">repo:</span>
            <span className="font-medium text-aubergine">filament/core</span>
            <span className="text-[10px] text-stone-muted font-mono">(local default)</span>
          </div>
        </div>

        {/* Search Entry Point */}
        <div className="flex-1 max-w-md mx-4">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-stone-muted" />
            <input
              type="text"
              placeholder="Search claims, evidence hashes, dependencies (Press /)"
              className="w-full bg-parchment border border-stone-border rounded-sm py-1.5 pl-8 pr-3 text-xs font-sans text-aubergine placeholder:text-stone-muted/80 focus:outline-none focus:border-copper focus:ring-1 focus:ring-copper/40 transition-all"
            />
          </div>
        </div>

        {/* Agent Auth / Key Configuration */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setInputKey(apiKey);
              setIsKeyModalOpen(true);
            }}
            className="flex items-center gap-2 px-2.5 py-1 text-xs font-mono rounded-sm border border-stone-border bg-parchment hover:border-copper text-aubergine transition-colors cursor-pointer"
            title="Configure Agent API Key for authenticated requests"
          >
            <Key className="w-3.5 h-3.5 text-copper" />
            <span>{apiKey ? 'Agent Key Set' : 'Configure API Key'}</span>
            <span className={`w-1.5 h-1.5 rounded-full ${apiKey ? 'bg-sage' : 'bg-citron'}`} />
          </button>

          <div className="w-7 h-7 rounded-sm bg-stone-light/60 border border-stone-border flex items-center justify-center text-aubergine-light text-xs font-mono font-medium">
            <Shield className="w-3.5 h-3.5 text-aubergine-light" />
          </div>
        </div>
      </header>

      {/* API Key Modal */}
      {isKeyModalOpen && (
        <div className="fixed inset-0 z-50 bg-aubergine-deep/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-parchment-light border border-stone-border rounded-sm max-w-md w-full shadow-lg overflow-hidden animate-in fade-in duration-150">
            <div className="px-5 py-4 border-b border-stone-border bg-parchment flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Key className="w-4 h-4 text-copper" />
                <h3 className="font-editorial text-lg text-aubergine font-medium">Agent Authentication</h3>
              </div>
              <button
                onClick={() => setIsKeyModalOpen(false)}
                className="text-stone-muted hover:text-aubergine text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveKey} className="p-5 space-y-4">
              <p className="text-xs text-stone-muted leading-relaxed">
                Requests to Filament's memory endpoints require a valid Agent Bearer API key. Paste your active agent token below to query live claims or record reverifications.
              </p>

              <div>
                <label className="block text-xs font-mono text-aubergine mb-1 font-medium">
                  Bearer API Token
                </label>
                <input
                  type="password"
                  value={inputKey}
                  onChange={(e) => setInputKey(e.target.value)}
                  placeholder="e.g. fil_live_agent_key_..."
                  className="w-full bg-parchment border border-stone-border rounded-sm py-1.5 px-3 text-xs font-mono text-aubergine placeholder:text-stone-muted focus:outline-none focus:border-copper focus:ring-1 focus:ring-copper/40"
                />
              </div>

              <div className="flex items-center justify-between gap-2 pt-2 border-t border-stone-border/60">
                <div>
                  {apiKey && (
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      onClick={() => {
                        setApiKey('');
                        setInputKey('');
                        setIsKeyModalOpen(false);
                      }}
                    >
                      Clear Token
                    </Button>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setIsKeyModalOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" size="sm">
                    Save Credentials
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
