import React from 'react';
import { Card } from '../components/common/Card';

export const IntegrationsPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      <div className="border-b border-stone-border pb-5">
        <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
          <span className="w-2 h-2 rounded-full bg-copper inline-block" />
          <span>Integrations & Sources</span>
        </div>
        <h1 className="font-editorial text-3xl text-aubergine font-normal">
          Environment Ingestion Adapters
        </h1>
        <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl">
          Automated hooks for reporting environment snapshots from CI pipelines, CLI agents, and MCP adapters.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card title="CI/CD Webhooks" subtitle="GitHub Actions, GitLab CI">
          <p className="text-xs text-stone-muted leading-relaxed font-sans mb-4">
            Automatically ingest environment snapshots upon pull request merge or deploy.
          </p>
          <span className="text-[11px] font-mono text-stone-muted px-2 py-0.5 rounded-sm bg-parchment border border-stone-border">
            POST /api/v1/snapshots
          </span>
        </Card>

        <Card title="Agent MCP Tooling" subtitle="Model Context Protocol">
          <p className="text-xs text-stone-muted leading-relaxed font-sans mb-4">
            Enable agents to inspect and reverify conditions before acting on memory claims.
          </p>
          <span className="text-[11px] font-mono text-stone-muted px-2 py-0.5 rounded-sm bg-parchment border border-stone-border">
            mcp-server-filament
          </span>
        </Card>

        <Card title="Filament CLI" subtitle="Local developer tool">
          <p className="text-xs text-stone-muted leading-relaxed font-sans mb-4">
            Scan local workspaces and compute file digests with canonical path boundaries.
          </p>
          <span className="text-[11px] font-mono text-stone-muted px-2 py-0.5 rounded-sm bg-parchment border border-stone-border">
            filament scan .
          </span>
        </Card>
      </div>
    </div>
  );
};
