import React from 'react';
import { Card } from '../components/common/Card';
import { CheckCircle2, Clock } from 'lucide-react';

export const IntegrationsPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      {/* Header Banner */}
      <div className="border-b border-stone-border pb-5">
        <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
          <span className="w-2 h-2 rounded-full bg-copper inline-block animate-pulse" />
          <span>Ingestion Adapters & Connectors</span>
        </div>
        <h1 className="font-editorial text-3xl md:text-4xl text-charcoal font-normal">
          Integrations & Ingestion Adapters
        </h1>
        <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl leading-relaxed">
          Automated hooks for reporting environment state, git digests, and tool outputs from CI pipelines, CLI agents, and MCP adapters.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Active: FastAPI REST Gateway */}
        <Card
          title="FastAPI REST Gateway"
          subtitle="Direct Workspace API"
          badge={<span className="w-2 h-2 rounded-full bg-sage" />}
        >
          <div className="space-y-3">
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-xs bg-sage/15 text-sage-dark font-mono text-[11px] font-medium">
              <CheckCircle2 className="w-3 h-3" />
              <span>Active & Connected</span>
            </div>
            <p className="text-xs text-stone-muted leading-relaxed font-sans">
              Connect external AI agents, autonomous scripts, and background jobs to record memories, attach evidence, and run validity evaluations.
            </p>
            <div className="text-[11px] font-mono text-copper bg-bone p-2 rounded-sm border border-stone-border">
              POST /api/v1/claims
            </div>
          </div>
        </Card>

        {/* Planned: CI/CD Webhooks */}
        <Card
          title="CI/CD Webhooks"
          subtitle="GitHub Actions & GitLab CI"
          badge={<span className="w-2 h-2 rounded-full bg-brass" />}
        >
          <div className="space-y-3">
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-xs bg-brass/15 text-brass-dark font-mono text-[11px] font-medium">
              <Clock className="w-3 h-3" />
              <span>Configurable Adapter</span>
            </div>
            <p className="text-xs text-stone-muted leading-relaxed font-sans">
              Automatically report environment snapshots and commit digests upon merge or deploy, triggering automatic drift evaluations.
            </p>
            <div className="text-[11px] font-mono text-stone-muted bg-bone p-2 rounded-sm border border-stone-border">
              POST /api/v1/snapshots
            </div>
          </div>
        </Card>

        {/* Planned: MCP Tooling */}
        <Card
          title="Model Context Protocol (MCP)"
          subtitle="Agent Tooling Server"
          badge={<span className="w-2 h-2 rounded-full bg-brass" />}
        >
          <div className="space-y-3">
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-xs bg-brass/15 text-brass-dark font-mono text-[11px] font-medium">
              <Clock className="w-3 h-3" />
              <span>In Development</span>
            </div>
            <p className="text-xs text-stone-muted leading-relaxed font-sans">
              Enables LLM agents like Claude, Gemini, and Muse to inspect validity and query governed memories natively via tool calls.
            </p>
            <div className="text-[11px] font-mono text-stone-muted bg-bone p-2 rounded-sm border border-stone-border">
              mcp-server-filament
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
