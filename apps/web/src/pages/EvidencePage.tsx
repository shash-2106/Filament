import React from 'react';
import { ShieldCheck, FileCode, GitCommit, MessageSquare, Terminal } from 'lucide-react';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';

export const EvidencePage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      <div className="border-b border-stone-border pb-5">
        <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
          <span className="w-2 h-2 rounded-full bg-copper inline-block" />
          <span>Evidence Ledger</span>
        </div>
        <h1 className="font-editorial text-3xl text-aubergine font-normal">
          Immutable Evidence Artifacts
        </h1>
        <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl">
          Content-addressed source artifacts, git commits, and tool outputs providing cryptographic grounding for memory claims.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-parchment-light border-stone-border">
          <div className="text-stone-muted text-xs font-mono uppercase tracking-wider mb-1">
            Supported Artifact Types
          </div>
          <div className="text-sm font-sans text-aubergine mt-2 space-y-1">
            <div className="flex items-center gap-2"><FileCode className="w-3.5 h-3.5 text-copper" /> File Snippets</div>
            <div className="flex items-center gap-2"><GitCommit className="w-3.5 h-3.5 text-copper" /> Git Commits</div>
            <div className="flex items-center gap-2"><MessageSquare className="w-3.5 h-3.5 text-copper" /> User Turns</div>
            <div className="flex items-center gap-2"><Terminal className="w-3.5 h-3.5 text-copper" /> Tool Outputs</div>
          </div>
        </Card>

        <div className="md:col-span-3">
          <Card title="Workspace Evidence Index">
            <EmptyState
              icon={ShieldCheck}
              title="Evidence Browsing Capability Pending"
              description="Evidence ingestion is active via POST /api/v1/evidence and claims link directly to evidence. Dedicated evidence catalog search and bulk artifact inspection endpoints will be connected in Phase 2."
              unconnectedNotice={true}
            />
          </Card>
        </div>
      </div>
    </div>
  );
};

