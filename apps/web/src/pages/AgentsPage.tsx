import React from 'react';
import { Bot } from 'lucide-react';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';

export const AgentsPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      <div className="border-b border-stone-border pb-5">
        <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
          <span className="w-2 h-2 rounded-full bg-copper inline-block" />
          <span>Actor Boundary</span>
        </div>
        <h1 className="font-editorial text-3xl text-aubergine font-normal">
          Agent Identity & Scopes
        </h1>
        <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl">
          Authorized agent actors, cryptographic API key hashes, and default visibility scopes.
        </p>
      </div>

      <Card title="Workspace Agent Registry">
        <EmptyState
          icon={Bot}
          title="Agent Management Endpoint Pending"
          description="Agents authenticate using constant-time hashed Bearer tokens. Agent lifecycle and permission management routes (GET /api/v1/agents) are scheduled for Phase 3."
          unconnectedNotice={true}
        />
      </Card>
    </div>
  );
};
