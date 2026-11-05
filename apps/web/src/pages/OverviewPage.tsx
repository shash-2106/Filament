import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Compass,
  Database,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';
import { useClaimsQuery } from '../api/queries';
import { useAuth } from '../context/auth';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { EmptyState } from '../components/common/EmptyState';

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const { workspaceName } = useAuth();

  const { data: claims, isLoading: claimsLoading } = useClaimsQuery({ limit: 50 });

  const currentCount = claims?.filter((c) => c.status === 'current').length || 0;
  const reviewCount = claims?.filter((c) => c.status === 'needs_review').length || 0;
  const disputedCount = claims?.filter((c) => c.status === 'disputed').length || 0;

  const needsReviewClaims = claims?.filter((c) => c.status === 'needs_review') || [];

  return (
    <div className="space-y-6">
      {/* Overview Masthead */}
      <div className="bg-[#14231D] border border-[#294537] rounded-lg p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="font-heading text-2xl font-bold tracking-tight text-graphite-text">
              Workspace Control Centre
            </h1>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#1C3027] text-phosphor border border-[#294537]">
              {workspaceName || 'Default Workspace'}
            </span>
          </div>
          <p className="text-xs text-graphite-text-secondary font-sans leading-relaxed max-w-2xl">
            Filament actively monitors AI knowledge: auditing evidence provenance, testing required
            environmental conditions, and alerting on configuration drift.
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate('/memory')}
            icon={<Database className="w-3.5 h-3.5" />}
          >
            Explore Memories
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate('/guide')}
            icon={<Compass className="w-3.5 h-3.5 text-phosphor" />}
          >
            Interactive Tour
          </Button>
        </div>
      </div>

      {/* KPI Metric Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <div className="bg-[#14231D] border border-[#294537] rounded p-4 space-y-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-graphite-text-tertiary">
            Active Memories
          </div>
          <div className="text-2xl font-heading font-bold text-phosphor">
            {claimsLoading ? '...' : currentCount}
          </div>
          <div className="text-[11px] font-sans text-graphite-text-secondary">
            Verified applicable
          </div>
        </div>

        <div className="bg-[#14231D] border border-[#294537] rounded p-4 space-y-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-[#E5B45E]">
            Needs Review
          </div>
          <div className="text-2xl font-heading font-bold text-[#E5B45E]">
            {claimsLoading ? '...' : reviewCount}
          </div>
          <div className="text-[11px] font-sans text-graphite-text-secondary">
            Condition drift detected
          </div>
        </div>

        <div className="bg-[#14231D] border border-[#294537] rounded p-4 space-y-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-[#A96580]">
            Disputed Claims
          </div>
          <div className="text-2xl font-heading font-bold text-[#A96580]">
            {claimsLoading ? '...' : disputedCount}
          </div>
          <div className="text-[11px] font-sans text-graphite-text-secondary">
            Requires resolution
          </div>
        </div>

        <div className="bg-[#14231D] border border-[#294537] rounded p-4 space-y-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-graphite-text-tertiary">
            Connected Agents
          </div>
          <div className="text-2xl font-heading font-bold text-graphite-text">
            1
          </div>
          <div className="text-[11px] font-sans text-graphite-text-secondary">
            Active participants
          </div>
        </div>
      </div>

      {/* Needs Review / Attention Queue */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-[#E5B45E]" />
            <h2 className="font-heading text-base font-semibold text-graphite-text">
              Needs Review / Attention Queue
            </h2>
          </div>
          {reviewCount > 0 && (
            <span className="text-xs font-mono text-[#E5B45E]">
              {reviewCount} memories require verification
            </span>
          )}
        </div>

        {needsReviewClaims.length > 0 ? (
          <div className="bg-[#14231D] border border-[#294537] rounded divide-y divide-[#1F362B]">
            {needsReviewClaims.map((claim) => (
              <div
                key={claim.id}
                onClick={() => navigate(`/memory?claim=${claim.id}`)}
                className="p-3.5 flex items-center justify-between gap-4 hover:bg-[#192C23] cursor-pointer transition-colors"
              >
                <div className="space-y-1 max-w-2xl">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-phosphor">
                      {claim.subject} : {claim.predicate}
                    </span>
                    <Badge variant="type" type={claim.claim_type}>
                      {claim.claim_type}
                    </Badge>
                  </div>
                  <p className="text-xs text-graphite-text font-sans line-clamp-1">
                    {claim.raw_statement}
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <Badge variant="status" status={claim.status}>
                    needs review
                  </Badge>
                  <ArrowRight className="w-4 h-4 text-graphite-text-tertiary" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 bg-[#14231D] border border-[#294537] rounded text-center text-xs font-mono text-graphite-text-tertiary">
            <span>All memories healthy</span>. No environmental drift detected across active claims.
          </div>
        )}
      </div>

      {/* Recent Agent Memories */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-phosphor" />
            <h2 className="font-heading text-base font-semibold text-graphite-text">
              Recent Agent Memories
            </h2>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/memory')}
            icon={<ArrowRight className="w-3.5 h-3.5 text-phosphor" />}
          >
            View All Memories
          </Button>
        </div>

        {claims && claims.length > 0 ? (
          <div className="bg-[#14231D] border border-[#294537] rounded divide-y divide-[#1F362B]">
            {claims.slice(0, 6).map((claim) => (
              <div
                key={claim.id}
                onClick={() => navigate(`/memory?claim=${claim.id}`)}
                className="p-3.5 flex items-center justify-between gap-4 hover:bg-[#192C23] cursor-pointer transition-colors text-xs"
              >
                <div className="space-y-1 max-w-2xl">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold text-graphite-text">
                      {claim.subject} : {claim.predicate}
                    </span>
                    <Badge variant="type" type={claim.claim_type}>
                      {claim.claim_type}
                    </Badge>
                  </div>
                  <p className="text-graphite-text-secondary font-sans line-clamp-1">
                    {claim.raw_statement}
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <Badge variant="status" status={claim.status}>
                    {claim.status}
                  </Badge>
                  <span className="font-mono text-[10px] text-graphite-text-tertiary">
                    v{claim.version}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No Memories Recorded Yet"
            description="Extract candidate memories with Muse Spark or record assertions directly from agents."
            actionLabel="Open Memory Workstation"
            onAction={() => navigate('/memory')}
          />
        )}
      </div>
    </div>
  );
};
