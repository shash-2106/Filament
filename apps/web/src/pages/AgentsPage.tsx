import React from 'react';
import { Bot, CheckCircle2 } from 'lucide-react';
import { useAgentsQuery } from '../api/queries';
import { useAuth } from '../context/auth';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';

export const AgentsPage: React.FC = () => {
  const { isConfigured, currentAgentId } = useAuth();
  const { data: agents, isLoading, isError, error } = useAgentsQuery();

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      {/* Header Banner */}
      <div className="border-b border-stone-border pb-5">
        <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
          <span className="w-2 h-2 rounded-full bg-copper inline-block animate-pulse" />
          <span>Actor Boundary & Security Ledger</span>
        </div>
        <h1 className="font-editorial text-3xl md:text-4xl text-charcoal font-normal">
          Connected AI Agents
        </h1>
        <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl leading-relaxed">
          Authorized agent actors, cryptographic API key hashes, and default visibility scopes registered in this workspace.
        </p>
      </div>

      {!isConfigured ? (
        <Card title="Workspace Agent Registry">
          <EmptyState
            icon={Bot}
            title="Authentication Required"
            description="Configure your Agent Bearer API key in the header to view registered workspace agents."
          />
        </Card>
      ) : isLoading ? (
        <div className="py-24 text-center text-xs font-mono text-stone-muted animate-pulse">
          Loading authorized workspace agents...
        </div>
      ) : isError ? (
        <div className="p-4 rounded-sm bg-terracotta/10 border border-terracotta/30 text-xs font-mono text-terracotta-dark">
          Failed to load agents: {error?.message}
        </div>
      ) : agents && agents.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => {
            const isCurrent = currentAgentId === agent.id;
            return (
              <Card
                key={agent.id}
                className={`bg-bone-light border-stone-border transition-all ${
                  isCurrent ? 'ring-1 ring-copper border-copper shadow-xs' : 'hover:border-stone-dark'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-sm bg-bone border border-stone-border flex items-center justify-center text-copper shadow-xs">
                      <Bot className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <h3 className="font-editorial text-lg text-charcoal font-medium leading-none">
                          {agent.name}
                        </h3>
                        {isCurrent && (
                          <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-xs bg-copper text-bone-light font-medium">
                            Active
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] font-mono text-stone-muted">
                        {agent.id.slice(0, 10)}...
                      </span>
                    </div>
                  </div>

                  <span className="inline-flex items-center gap-1 text-[11px] font-mono text-sage">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>active</span>
                  </span>
                </div>

                <div className="space-y-2 border-t border-stone-border/70 pt-3 text-xs font-mono">
                  <div className="flex items-center justify-between text-stone-muted">
                    <span>Default Scope:</span>
                    <span className="text-charcoal font-medium">{agent.default_scope}</span>
                  </div>

                  <div className="flex items-center justify-between text-stone-muted">
                    <span>Registered:</span>
                    <span className="text-charcoal">{new Date(agent.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card title="Workspace Agent Registry">
          <EmptyState
            icon={Bot}
            title="No Agents Registered"
            description="No active agent credentials found in this workspace."
          />
        </Card>
      )}
    </div>
  );
};
