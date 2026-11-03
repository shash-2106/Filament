import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldAlert,
  ArrowRight,
  Database,
  History,
  GitBranch,
  Layers,
  KeyRound,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import { useClaimsQuery, useHealthQuery } from '../api/queries';
import { useAuth } from '../context/auth';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { EmptyState } from '../components/common/EmptyState';

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const { workspaceName, isConfigured } = useAuth();
  const { data: health } = useHealthQuery();

  // Retrieve real claims from backend
  const {
    data: allClaims,
    isLoading: claimsLoading,
    isError: claimsError,
    error: claimsErrorObj,
  } = useClaimsQuery({ limit: 10 });

  // Separate claims requiring review or disputed
  const reviewClaims = allClaims?.filter(
    (c) => c.status === 'needs_review' || c.status === 'disputed'
  ) || [];

  const currentClaims = allClaims?.filter((c) => c.status === 'current') || [];

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      {/* Workspace Identity Masthead */}
      <div className="border-b border-stone-border pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-copper inline-block" />
            <span>Workspace Control Centre</span>
          </div>
          <h1 className="font-editorial text-3xl md:text-4xl text-aubergine font-normal tracking-tight">
            {workspaceName}
          </h1>
          <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl leading-relaxed">
            Immutable memory assertions, condition-bound validity checks, and provenance lineage for autonomous agents.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate('/memory')}
            icon={<Database className="w-3.5 h-3.5" />}
          >
            Memory Browser
          </Button>
          <Button
            size="sm"
            onClick={() => navigate('/memory')}
            icon={<ArrowRight className="w-3.5 h-3.5" />}
          >
            Inspect Claims
          </Button>
        </div>
      </div>

      {/* Authentication Notice if not configured */}
      {!isConfigured && (
        <div className="p-4 rounded-sm bg-citron-tint border border-citron-border/70 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <KeyRound className="w-5 h-5 text-aubergine-light mt-0.5 flex-shrink-0" />
            <div>
              <h4 className="text-sm font-sans font-medium text-aubergine">
                No Agent API Key Configured in Workstation
              </h4>
              <p className="text-xs text-stone-muted mt-0.5 leading-relaxed">
                To query workspace memory or execute live condition evaluations, configure your agent Bearer API key in the header controls above.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Primary Telemetry Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Metric 1: Governed Memory Units */}
        <Card className="bg-parchment-light border-stone-border">
          <div className="flex items-center justify-between text-stone-muted mb-2">
            <span className="text-xs font-mono uppercase tracking-wider">Governed Claims</span>
            <Database className="w-4 h-4 text-copper" />
          </div>
          <div className="font-editorial text-3xl text-aubergine font-medium">
            {!isConfigured ? (
              <span className="text-stone-muted text-xl font-mono">—</span>
            ) : claimsLoading ? (
              <span className="text-stone-muted text-xl font-mono animate-pulse">Scanning...</span>
            ) : claimsError ? (
              <span className="text-terracotta text-lg font-mono">Error</span>
            ) : (
              allClaims?.length ?? 0
            )}
          </div>
          <div className="mt-2 text-xs text-stone-muted font-sans flex items-center justify-between">
            <span>{currentClaims.length} verified active</span>
            <span className="font-mono text-[11px] text-copper font-medium">{allClaims?.length ?? 0} total</span>
          </div>
        </Card>

        {/* Metric 2: Needs Review / Invalidation Queue */}
        <Card className="bg-parchment-light border-stone-border">
          <div className="flex items-center justify-between text-stone-muted mb-2">
            <span className="text-xs font-mono uppercase tracking-wider">Attention Required</span>
            <ShieldAlert className="w-4 h-4 text-terracotta" />
          </div>
          <div className="font-editorial text-3xl text-aubergine font-medium">
            {claimsLoading ? (
              <span className="text-stone-muted text-xl font-mono animate-pulse">Scanning...</span>
            ) : (
              reviewClaims.length
            )}
          </div>
          <div className="mt-2 text-xs text-stone-muted font-sans flex items-center justify-between">
            <span>Disputed or drifted</span>
            <Badge status={reviewClaims.length > 0 ? 'needs_review' : 'current'}>
              {reviewClaims.length > 0 ? 'action needed' : 'healthy'}
            </Badge>
          </div>
        </Card>

        {/* Metric 3: Condition Engine */}
        <Card className="bg-parchment-light border-stone-border">
          <div className="flex items-center justify-between text-stone-muted mb-2">
            <span className="text-xs font-mono uppercase tracking-wider">Validity Engine</span>
            <Sparkles className="w-4 h-4 text-sage" />
          </div>
          <div className="font-editorial text-2xl text-aubergine font-medium">
            Condition-Bound
          </div>
          <div className="mt-2 text-xs text-stone-muted font-sans flex items-center justify-between">
            <span>Deterministic checks</span>
            <span className="font-mono text-[11px] text-sage font-medium">active</span>
          </div>
        </Card>

        {/* Metric 4: Gateway Service */}
        <Card className="bg-parchment-light border-stone-border">
          <div className="flex items-center justify-between text-stone-muted mb-2">
            <span className="text-xs font-mono uppercase tracking-wider">Gateway State</span>
            <CheckCircle2 className="w-4 h-4 text-copper" />
          </div>
          <div className="font-editorial text-2xl text-aubergine font-medium capitalize">
            {health?.status || 'Online'}
          </div>
          <div className="mt-2 text-xs text-stone-muted font-sans flex items-center justify-between">
            <span>FastAPI asyncpg</span>
            <span className="font-mono text-[11px] text-copper">port 8000</span>
          </div>
        </Card>
      </div>

      {/* Main Content Layout: Two Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Recent Claims (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          <Card
            title="Recent Governed Claims"
            subtitle="Latest immutable memory assertions established within this workspace"
            actions={
              <button
                onClick={() => navigate('/memory')}
                className="text-xs font-mono text-copper hover:text-copper-hover flex items-center gap-1 cursor-pointer"
              >
                <span>View all</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            }
          >
            {!isConfigured ? (
              <div className="py-8 text-center text-xs font-mono text-stone-muted">
                Agent Bearer token required to load claims ledger.
              </div>
            ) : claimsLoading ? (
              <div className="py-8 text-center text-xs font-mono text-stone-muted animate-pulse">
                Querying live backend assertions...
              </div>
            ) : claimsError ? (
              <div className="p-4 rounded-sm bg-terracotta/10 border border-terracotta/30 text-xs text-terracotta-dark font-mono">
                Failed to load claims: {claimsErrorObj?.message || 'Unauthorized or connection error.'}
              </div>
            ) : allClaims && allClaims.length > 0 ? (
              <div className="divide-y divide-stone-border/60 -mx-4 -my-4">
                {allClaims.slice(0, 6).map((claim) => (
                  <div
                    key={claim.id}
                    onClick={() => navigate(`/memory?claim=${claim.id}`)}
                    className="p-4 hover:bg-parchment/60 transition-colors cursor-pointer flex items-center justify-between gap-4"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge type={claim.claim_type} />
                        <span className="font-mono text-xs font-semibold text-aubergine truncate">
                          {claim.subject}
                        </span>
                        <span className="font-mono text-xs text-stone-muted">→</span>
                        <span className="font-mono text-xs text-copper truncate">
                          {claim.predicate}
                        </span>
                      </div>
                      <p className="text-xs text-stone-muted line-clamp-1 font-sans">
                        {claim.raw_statement}
                      </p>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Badge status={claim.status} />
                      <span className="text-[11px] font-mono text-stone-muted px-1.5 py-0.5 rounded-sm bg-stone-light/50 border border-stone-border">
                        v{claim.version}
                        {claim.active_condition_version
                          ? ` (cond: v${claim.active_condition_version})`
                          : ''}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Database}
                title="No Memory Assertions Found"
                description="This workspace does not have any established claims yet. Agents record claims backed by immutable evidence."
                actionLabel="Explore Memory Browser"
                onAction={() => navigate('/memory')}
              />
            )}
          </Card>

          {/* Invalidation & Review Queue */}
          <Card
            title="Needs Review / Attention Queue"
            subtitle="Claims subject to upstream drift, supersession cascades, or human dispute"
            badge={
              reviewClaims.length > 0 ? (
                <span className="w-2 h-2 rounded-full bg-terracotta animate-pulse" />
              ) : null
            }
          >
            {reviewClaims.length > 0 ? (
              <div className="divide-y divide-stone-border/60 -mx-4 -my-4">
                {reviewClaims.map((claim) => (
                  <div
                    key={claim.id}
                    onClick={() => navigate(`/memory?claim=${claim.id}`)}
                    className="p-4 hover:bg-parchment/60 transition-colors cursor-pointer flex items-center justify-between gap-4"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge status={claim.status} />
                        <span className="font-mono text-xs font-semibold text-aubergine">
                          {claim.subject}
                        </span>
                      </div>
                      <p className="text-xs text-stone-muted line-clamp-1 font-sans">
                        {claim.raw_statement}
                      </p>
                    </div>
                    <Button size="sm" variant="secondary">
                      Inspect
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-stone-muted font-sans flex flex-col items-center">
                <CheckCircle2 className="w-6 h-6 text-sage mb-2" />
                <span className="font-medium text-aubergine">All claims healthy</span>
                <span className="mt-0.5">No claims are currently flagged for review or disputed.</span>
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Governance Status & Unconnected Endpoints (1 col) */}
        <div className="space-y-6">
          {/* Architectural Governance Principles Card */}
          <Card
            title="Validity Principles"
            subtitle="Core invariants enforced by Filament backend"
          >
            <ul className="space-y-3 text-xs text-aubergine-light font-sans">
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-copper mt-1.5 flex-shrink-0" />
                <span>
                  <strong className="text-aubergine font-medium">Condition-Bound Validity:</strong> Claims do not self-assert permanence; they declare exact environmental prerequisites.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-copper mt-1.5 flex-shrink-0" />
                <span>
                  <strong className="text-aubergine font-medium">Strict Append-Only History:</strong> Snapshots, condition sets, and verifications cannot be altered or deleted.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-copper mt-1.5 flex-shrink-0" />
                <span>
                  <strong className="text-aubergine font-medium">Server-Side Invalidation:</strong> Supersession cascades across dependency DAGs deterministically.
                </span>
              </li>
            </ul>
          </Card>

          {/* Pending Backend Capabilities (Explicitly showing unconnected capabilities) */}
          <Card
            title="Lineage & Audit Infrastructure"
            subtitle="Live status of governance subsystems"
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs p-2.5 rounded-sm bg-parchment border border-stone-border/70">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-copper" />
                  <span className="font-sans font-medium text-aubergine">Claims Ledger</span>
                </div>
                <span className="text-[11px] font-mono text-sage font-medium">Connected</span>
              </div>

              <div className="flex items-center justify-between text-xs p-2.5 rounded-sm bg-parchment border border-stone-border/70">
                <div className="flex items-center gap-2">
                  <GitBranch className="w-4 h-4 text-stone-muted" />
                  <span className="font-sans font-medium text-aubergine">Dependency DAG</span>
                </div>
                <span className="text-[11px] font-mono text-citron-dark font-medium">Read via Claims</span>
              </div>

              <div className="flex items-center justify-between text-xs p-2.5 rounded-sm bg-parchment border border-stone-border/70">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-stone-muted" />
                  <span className="font-sans font-medium text-aubergine">Evidence Catalog</span>
                </div>
                <span className="text-[11px] font-mono text-stone-muted">Linked to Claims</span>
              </div>

              <div className="flex items-center justify-between text-xs p-2.5 rounded-sm bg-parchment border border-stone-border/70">
                <div className="flex items-center gap-2">
                  <History className="w-4 h-4 text-stone-muted" />
                  <span className="font-sans font-medium text-aubergine">Audit Trail Stream</span>
                </div>
                <span className="text-[11px] font-mono text-stone-muted">Internal DB Trigger</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
