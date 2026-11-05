import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Search,
  RefreshCw,
  Plus,
  Filter,
  Sparkles,
  GitFork,
  ExternalLink,
} from 'lucide-react';
import { useClaimsQuery, useCreateClaimMutation } from '../api/queries';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { EmptyState } from '../components/common/EmptyState';
import { ClaimDrawer } from '../components/memory/ClaimDrawer';
import { ExtractMemoriesModal } from '../components/memory/ExtractMemoriesModal';

export const MemoryPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedClaimId = searchParams.get('claim');

  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showExtractModal, setShowExtractModal] = useState(false);
  const [newSubject, setNewSubject] = useState('');
  const [newPredicate, setNewPredicate] = useState('configured_with');
  const [newStatement, setNewStatement] = useState('');
  const [newType, setNewType] = useState('fact');
  const [newScope, setNewScope] = useState('team');
  const [newObjectVal, setNewObjectVal] = useState('{}');

  const createMutation = useCreateClaimMutation();

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

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubject.trim() || !newStatement.trim()) return;

    let parsedVal = {};
    try {
      parsedVal = JSON.parse(newObjectVal);
    } catch {
      parsedVal = { raw: newObjectVal };
    }

    createMutation.mutate(
      {
        claim_type: newType,
        subject: newSubject.trim(),
        predicate: newPredicate.trim(),
        object_value: parsedVal,
        raw_statement: newStatement.trim(),
        scope: newScope,
        confidence: 1.0,
      },
      {
        onSuccess: () => {
          setShowCreateModal(false);
          setNewSubject('');
          setNewStatement('');
          setNewObjectVal('{}');
        },
      }
    );
  };

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-[#294537]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-heading text-2xl font-bold tracking-tight text-graphite-text">
              Workspace Memories
            </h1>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#1C3027] text-phosphor border border-[#294537]">
              {claims ? `${claims.length} Governed` : 'Loading...'}
            </span>
          </div>
          <p className="text-xs text-graphite-text-secondary mt-1 font-sans">
            Condition-bound knowledge, decisions, and constraints actively audited against environmental drift.
          </p>
        </div>

        {/* Primary Actions */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowExtractModal(true)}
            icon={<Sparkles className="w-3.5 h-3.5" />}
          >
            Extract with Muse Spark
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowCreateModal(true)}
            icon={<Plus className="w-3.5 h-3.5 text-phosphor" />}
          >
            Record Memory
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin text-phosphor' : ''}`} />}
            title="Refresh memory store"
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-[#14231D] border border-[#294537] rounded p-3 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 flex-1 min-w-[240px]">
          <Search className="w-4 h-4 text-graphite-text-tertiary" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by statement, subject or predicate..."
            className="w-full bg-[#0B1210] border border-[#294537] rounded px-3 py-1.5 text-xs text-graphite-text placeholder:text-graphite-text-tertiary focus:outline-none focus:border-phosphor"
          />
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-mono text-[11px] text-graphite-text-tertiary">
            <Filter className="w-3.5 h-3.5 text-phosphor" />
            <span>STATUS:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-[#0B1210] border border-[#294537] rounded px-2 py-1 text-xs text-graphite-text focus:outline-none focus:border-phosphor font-mono"
            >
              <option value="all">All Statuses</option>
              <option value="current">Current (Applicable)</option>
              <option value="needs_review">Needs Review (Drifted)</option>
              <option value="disputed">Disputed</option>
              <option value="superseded">Superseded</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 font-mono text-[11px] text-graphite-text-tertiary">
            <span>TYPE:</span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-[#0B1210] border border-[#294537] rounded px-2 py-1 text-xs text-graphite-text focus:outline-none focus:border-phosphor font-mono"
            >
              <option value="all">All Types</option>
              <option value="fact">Fact</option>
              <option value="decision">Decision</option>
              <option value="constraint">Constraint</option>
              <option value="recommendation">Recommendation</option>
              <option value="preference">Preference</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Memory Table */}
      {isLoading ? (
        <div className="bg-[#14231D] border border-[#294537] rounded p-12 text-center text-xs font-mono text-graphite-text-tertiary animate-pulse">
          Loading governed memory store from Supabase...
        </div>
      ) : isError ? (
        <div className="bg-[#14231D] border border-[#A96580] rounded p-6 text-center text-xs space-y-2">
          <div className="text-[#A96580] font-semibold font-mono">Failed to load memories</div>
          <div className="text-graphite-text-secondary font-mono">{String(error)}</div>
          <Button variant="secondary" size="sm" onClick={() => refetch()}>
            Retry Connection
          </Button>
        </div>
      ) : filteredClaims && filteredClaims.length > 0 ? (
        <div className="bg-[#14231D] border border-[#294537] rounded overflow-hidden shadow-xs">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-[#111D18] border-b border-[#294537] font-mono text-[11px] text-graphite-text-tertiary uppercase tracking-wider">
                <th className="py-2.5 px-4">Subject & Predicate</th>
                <th className="py-2.5 px-4">Statement</th>
                <th className="py-2.5 px-3">Type</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Condition Version</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F362B]">
              {filteredClaims.map((claim) => (
                <tr
                  key={claim.id}
                  onClick={() => handleSelectClaim(claim.id)}
                  className={`cursor-pointer transition-colors ${
                    selectedClaimId === claim.id
                      ? 'bg-[#1C3027] border-l-2 border-l-phosphor'
                      : 'hover:bg-[#192C23]'
                  }`}
                >
                  <td className="py-3 px-4 font-mono">
                    <div className="font-semibold text-graphite-text">{claim.subject}</div>
                    <div className="text-[10px] text-graphite-text-tertiary">{claim.predicate}</div>
                  </td>
                  <td className="py-3 px-4 font-sans max-w-md">
                    <p className="text-graphite-text line-clamp-2 leading-relaxed">
                      {claim.raw_statement}
                    </p>
                  </td>
                  <td className="py-3 px-3">
                    <Badge variant="type" type={claim.claim_type}>
                      {claim.claim_type}
                    </Badge>
                  </td>
                  <td className="py-3 px-3">
                    <Badge variant="status" status={claim.status}>
                      {claim.status}
                    </Badge>
                  </td>
                  <td className="py-3 px-3 font-mono text-[11px] text-graphite-text-secondary">
                    {claim.active_condition_version ? (
                      <span className="flex items-center gap-1 text-phosphor">
                        <GitFork className="w-3 h-3 text-phosphor" />
                        v{claim.version} (req: v{claim.active_condition_version})
                      </span>
                    ) : (
                      <span className="text-graphite-text-tertiary">v{claim.version} (unbound)</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectClaim(claim.id);
                      }}
                      icon={<ExternalLink className="w-3 h-3 text-phosphor" />}
                    >
                      Inspect
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No Memories Found"
          description="No memories match your active filter. Use Muse Spark extraction to parse conversation transcripts into candidate memories."
          actionLabel="Extract with Muse Spark"
          onAction={() => setShowExtractModal(true)}
        />
      )}

      {/* Slide-out Inspection Drawer */}
      {selectedClaimId && (
        <ClaimDrawer claimId={selectedClaimId} onClose={handleCloseDrawer} />
      )}

      {/* Muse Extraction Modal */}
      <ExtractMemoriesModal
        isOpen={showExtractModal}
        onClose={() => setShowExtractModal(false)}
        onMemoryApproved={() => refetch()}
      />

      {/* Manual Memory Creation Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
          <div className="bg-[#14231D] border border-[#294537] rounded-md max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-[#294537]">
              <h3 className="font-heading text-lg font-semibold text-graphite-text">
                Record New Governed Memory
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-graphite-text-tertiary hover:text-graphite-text"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-3.5 text-xs font-sans">
              <div>
                <label className="block text-[11px] font-mono text-graphite-text-tertiary uppercase mb-1">
                  Subject (Entity or Component)
                </label>
                <input
                  type="text"
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  placeholder="e.g. pgvector_connection_pool"
                  className="w-full bg-[#0B1210] border border-[#294537] rounded px-3 py-1.5 text-graphite-text font-mono focus:outline-none focus:border-phosphor"
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono text-graphite-text-tertiary uppercase mb-1">
                  Predicate
                </label>
                <input
                  type="text"
                  value={newPredicate}
                  onChange={(e) => setNewPredicate(e.target.value)}
                  placeholder="e.g. max_connections"
                  className="w-full bg-[#0B1210] border border-[#294537] rounded px-3 py-1.5 text-graphite-text font-mono focus:outline-none focus:border-phosphor"
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-mono text-graphite-text-tertiary uppercase mb-1">
                  Human-Readable Statement
                </label>
                <textarea
                  value={newStatement}
                  onChange={(e) => setNewStatement(e.target.value)}
                  rows={3}
                  placeholder="State the assertion or decision clearly..."
                  className="w-full bg-[#0B1210] border border-[#294537] rounded px-3 py-1.5 text-graphite-text focus:outline-none focus:border-phosphor"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-mono text-graphite-text-tertiary uppercase mb-1">
                    Assertion Type
                  </label>
                  <select
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
                    className="w-full bg-[#0B1210] border border-[#294537] rounded px-2 py-1.5 text-graphite-text font-mono focus:outline-none focus:border-phosphor"
                  >
                    <option value="fact">Fact</option>
                    <option value="decision">Decision</option>
                    <option value="constraint">Constraint</option>
                    <option value="recommendation">Recommendation</option>
                    <option value="preference">Preference</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-mono text-graphite-text-tertiary uppercase mb-1">
                    Scope
                  </label>
                  <select
                    value={newScope}
                    onChange={(e) => setNewScope(e.target.value)}
                    className="w-full bg-[#0B1210] border border-[#294537] rounded px-2 py-1.5 text-graphite-text font-mono focus:outline-none focus:border-phosphor"
                  >
                    <option value="team">Team</option>
                    <option value="workspace">Workspace</option>
                    <option value="private">Private</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-[#294537]">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={createMutation.isPending}
                >
                  {createMutation.isPending ? 'Recording...' : 'Record Claim'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
