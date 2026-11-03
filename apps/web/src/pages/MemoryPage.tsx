import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Database,
  Search,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { useClaimsQuery } from '../api/queries';
import { useAuth } from '../context/auth';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { EmptyState } from '../components/common/EmptyState';
import { ClaimDrawer } from '../components/memory/ClaimDrawer';

export const MemoryPage: React.FC = () => {
  const { isConfigured } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedClaimId = searchParams.get('claim');

  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const {
    data: claims,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useClaimsQuery({
    status: statusFilter === 'all' ? undefined : statusFilter,
    claim_type: typeFilter === 'all' ? undefined : typeFilter,
    limit: 50,
  });

  const filteredClaims = claims?.filter((claim) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      claim.subject.toLowerCase().includes(q) ||
      claim.predicate.toLowerCase().includes(q) ||
      claim.raw_statement.toLowerCase().includes(q)
    );
  });

  const handleSelectClaim = (id: string) => {
    setSearchParams({ claim: id });
  };

  const handleCloseDrawer = () => {
    setSearchParams({});
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      {/* Page Header */}
      <div className="border-b border-stone-border pb-5 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-copper inline-block" />
            <span>Memory Browser</span>
          </div>
          <h1 className="font-editorial text-3xl text-aubergine font-normal">
            Governed Memory Ledger
          </h1>
          <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl">
            Audit, inspect, and evaluate immutable claim assertions, condition versions, and evidentiary lineages.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />}
          >
            Refresh Ledger
          </Button>
        </div>
      </div>

      {/* Filter and Control Bar */}
      <div className="p-3 bg-parchment-light border border-stone-border rounded-sm flex flex-col md:flex-row items-center justify-between gap-3">
        {/* Search Input */}
        <div className="relative w-full md:w-80">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-stone-muted" />
          <input
            type="text"
            placeholder="Filter by subject, predicate or text..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-parchment border border-stone-border rounded-sm py-1.5 pl-8 pr-3 text-xs font-sans text-aubergine placeholder:text-stone-muted focus:outline-none focus:border-copper"
          />
        </div>

        {/* Filter Dropdowns */}
        <div className="flex items-center gap-3 w-full md:w-auto">
          {/* Status Filter */}
          <div className="flex items-center gap-1.5 text-xs font-mono text-aubergine">
            <span className="text-stone-muted">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-parchment border border-stone-border rounded-sm py-1 px-2 text-xs font-mono text-aubergine focus:outline-none focus:border-copper cursor-pointer"
            >
              <option value="all">All States</option>
              <option value="current">Current (Verified)</option>
              <option value="needs_review">Needs Review</option>
              <option value="disputed">Disputed</option>
              <option value="superseded">Superseded</option>
              <option value="retracted">Retracted</option>
            </select>
          </div>

          {/* Type Filter */}
          <div className="flex items-center gap-1.5 text-xs font-mono text-aubergine">
            <span className="text-stone-muted">Type:</span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-parchment border border-stone-border rounded-sm py-1 px-2 text-xs font-mono text-aubergine focus:outline-none focus:border-copper cursor-pointer"
            >
              <option value="all">All Types</option>
              <option value="fact">Fact</option>
              <option value="recommendation">Recommendation</option>
              <option value="decision">Decision</option>
              <option value="preference">Preference</option>
              <option value="constraint">Constraint</option>
            </select>
          </div>
        </div>
      </div>

      {/* Claims Ledger Table */}
      <div className="bg-parchment-light border border-stone-border rounded-sm overflow-hidden">
        {!isConfigured ? (
          <div className="py-16 text-center text-xs font-mono text-stone-muted space-y-2">
            <div className="font-medium text-aubergine">Authentication Required</div>
            <div>Configure an authorized Agent Bearer token in the header controls to inspect this workspace.</div>
          </div>
        ) : isLoading ? (
          <div className="py-16 text-center text-xs font-mono text-stone-muted animate-pulse">
            Querying immutable claims ledger...
          </div>
        ) : isError ? (
          <div className="p-8 text-center text-xs font-mono text-terracotta space-y-2">
            <div>Failed to load claims: {error?.message}</div>
            <div className="text-stone-muted">Ensure an authorized Agent API key is configured.</div>
          </div>
        ) : filteredClaims && filteredClaims.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-stone-border bg-parchment/80 text-[11px] font-mono uppercase tracking-wider text-stone-muted">
                  <th className="py-2.5 px-4 font-medium">Type</th>
                  <th className="py-2.5 px-4 font-medium">Subject & Predicate</th>
                  <th className="py-2.5 px-4 font-medium">Assertion Summary</th>
                  <th className="py-2.5 px-4 font-medium">Status</th>
                  <th className="py-2.5 px-4 font-medium">Scope</th>
                  <th className="py-2.5 px-4 font-medium">Condition Set</th>
                  <th className="py-2.5 px-4 font-medium text-right">Version</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-border/60 text-xs">
                {filteredClaims.map((claim) => {
                  const isSelected = claim.id === selectedClaimId;
                  return (
                    <tr
                      key={claim.id}
                      onClick={() => handleSelectClaim(claim.id)}
                      className={`cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-copper-tint/50 border-l-2 border-l-copper'
                          : 'hover:bg-parchment/60'
                      }`}
                    >
                      {/* Type Badge */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <Badge type={claim.claim_type} />
                      </td>

                      {/* Subject & Predicate */}
                      <td className="py-3 px-4 whitespace-nowrap font-mono">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-aubergine">{claim.subject}</span>
                          <span className="text-stone-muted">→</span>
                          <span className="text-copper font-medium">{claim.predicate}</span>
                        </div>
                      </td>

                      {/* Assertion Statement */}
                      <td className="py-3 px-4 max-w-md font-sans">
                        <p className="line-clamp-1 text-aubergine-light">
                          {claim.raw_statement}
                        </p>
                      </td>

                      {/* Status */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <Badge status={claim.status} />
                      </td>

                      {/* Scope */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <Badge scope={claim.scope} />
                      </td>

                      {/* Condition Bound Status */}
                      <td className="py-3 px-4 whitespace-nowrap font-mono">
                        {claim.active_condition_version ? (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm bg-citron/20 text-aubergine text-[11px] font-medium border border-citron-dark/30">
                            <Sparkles className="w-2.5 h-2.5 text-copper" />
                            set v{claim.active_condition_version}
                          </span>
                        ) : (
                          <span className="text-stone-muted text-[11px]">—</span>
                        )}
                      </td>

                      {/* Version & Action */}
                      <td className="py-3 px-4 whitespace-nowrap text-right font-mono text-stone-muted">
                        v{claim.version}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={Database}
            title="No Claims Found"
            description={
              searchQuery || statusFilter !== 'all' || typeFilter !== 'all'
                ? 'No claims matched the applied filter criteria.'
                : 'No memory assertions exist in this workspace yet.'
            }
            actionLabel={
              searchQuery || statusFilter !== 'all' || typeFilter !== 'all'
                ? 'Clear Filters'
                : undefined
            }
            onAction={() => {
              setSearchQuery('');
              setStatusFilter('all');
              setTypeFilter('all');
            }}
          />
        )}
      </div>

      {/* Claim Detail Inspection Drawer */}
      <ClaimDrawer claimId={selectedClaimId} onClose={handleCloseDrawer} />
    </div>
  );
};
